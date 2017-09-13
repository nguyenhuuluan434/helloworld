#!/usr/bin/python

import os
import sys
import pytz
import json
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.sql import text

import paramiko
import ConfigParser

from keystoneauth1.identity import v3
from keystoneauth1 import session
from neutronclient.v2_0 import client as neutronclient

import logging

logging.basicConfig(filename="/opt/scripts/updatelb.log", level=logging.INFO)
log = logging.getLogger()

Config = ConfigParser.ConfigParser()

if not os.path.isfile("/opt/scripts/config_lb.ini"):
    print "File config config_lb.ini not exist \n"
    exit(0)
else:
    Config.read("/opt/scripts/config_lb.ini")


def ConfigSectionMap(section):
    dict = {}
    options = Config.options(section)
    for option in options:
        try:
            dict[option] = Config.get(section, option)
        except:
            dict[option] = None
    return dict


def GetDateTime(timezone):
    return str(datetime.strftime(datetime.now(pytz.timezone(timezone)), "%Y-%m-%d %H:%M:%S"));


def GetDateTimeObject(time):
    return datetime.strptime(time, "%Y-%m-%d %H:%M:%S");


def PingCheck(server):
    response = os.system("ping -c 2 " + server)
    if response == 0:
        return True
    else:
        return False


options_lb = ConfigSectionMap("config_lb");
options_ops = ConfigSectionMap("config_ops")

auth = v3.Password(auth_url=options_ops['os_auth_url'],
                   username=options_ops['os_username'],
                   password=options_ops['os_password'],
                   project_name=options_ops['os_project_name'],
                   user_domain_id=options_ops['os_user_domain_id'],
                   project_domain_id=options_ops['os_project_domain_id'])

sess = session.Session(auth=auth)

backup_host_lv1 = options_lb['backup_host_lv1'];
backup_host_lv2 = options_lb['backup_host_lv2'];

log.info(GetDateTime("Asia/Ho_Chi_Minh") + " current backup host lv1 is " + backup_host_lv1);
log.info(GetDateTime("Asia/Ho_Chi_Minh") + " current backup host lv2 is " + backup_host_lv2);

neutron = neutronclient.Client(session=sess)
agents = neutron.list_agents()["agents"];
agent_faileds = []
for agent in agents:
    if agent['binary'] == 'neutron-lbaasv2-agent':
        now = GetDateTimeObject(GetDateTime('Utc'))
        heartbeat = GetDateTimeObject(agent['heartbeat_timestamp']);
        # def __new__(cls, days=None, seconds=None, microseconds=None, milliseconds=None, minutes=None, hours=None, weeks=None):
        if now - timedelta(seconds=30) > heartbeat:
            agent_faileds.append(agent)

print agent_faileds
# check no agent fail and out process
if agent_faileds.__len__() == 0:
    print agent_faileds.__len__()
    log.info(GetDateTime("Asia/Ho_Chi_Minh") + " System is normal");
    exit(0)

log.info(GetDateTime("Asia/Ho_Chi_Minh") + " Process host fail");

for agent in agent_faileds:
    log.error(GetDateTime("Asia/Ho_Chi_Minh") + " Had problems on " + agent["host"]);

engine = create_engine('mysql://root:123L456@10.10.0.2:3306')
connection = engine.connect()

lb_agents = {}

for agent in agents:
    if agent['binary'] == 'neutron-lbaasv2-agent':
        print agent
        lb_agents[agent['host']] = agent['id'];
print lb_agents
print "\n"

sqlQuerySelect = "SELECT * FROM neutron.lbaas_loadbalanceragentbindings;";
agentbindings = connection.execute(text(sqlQuerySelect)).fetchall();

sqlQueryUpdate = 'UPDATE neutron.lbaas_loadbalanceragentbindings' \
                 ' SET neutron.lbaas_loadbalanceragentbindings.agent_id = \"%s\" ' \
                 ' WHERE neutron.lbaas_loadbalanceragentbindings.agent_id = \"%s\" ' \
                 ' AND neutron.lbaas_loadbalanceragentbindings.loadbalancer_id = \"%s\" ;'

for agent in agents:
    if agent['host'] == backup_host_lv1 or agent['host'] == backup_host_lv2:
        neutron.update_agent(agent['id'], body=json.loads('{"agent": {"admin_state_up": true}}'))

#find backup host
host_backup = "";
for agent in agents:
    if agent['admin_state_up'] == True and agent['alive'] == True and agent['host'] == backup_host_lv1 and PingCheck(
            agent['host']) == True:
        host_backup = backup_host_lv1;
        break;
    if agent['admin_state_up'] == True and agent['alive'] == True and agent['host'] == backup_host_lv2 and PingCheck(
            agent['host']) == True:
        host_backup = backup_host_lv2;
        break;

lb_failed = []
for agent_failed in agent_faileds:
    for row in agentbindings:
        if str(row[1]).__contains__(lb_agents.get(agent_failed["host"])) and str(row[1]).__eq__(
                lb_agents.get(agent_failed["host"])):
            lb_failed.append(row[0])

for agent_failed in agent_faileds:
    for lb in lb_failed:
        cmd = sqlQueryUpdate % (lb_agents.get(host_backup), lb_agents.get(agent_failed['host']), lb);
        print cmd
        log.info(GetDateTime("Asia/Ho_Chi_Minh") + " " + cmd);
        # resources = connection.execute(text(cmd))

exit(0);
# restart loadbalancer agent on backup host
try:
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    key = paramiko.RSAKey.from_private_key_file("/root/.ssh/id_rsa")
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print('*** Connecting to %s...***' % sys.argv[2])
    client.connect(host_backup, username="root", pkey=key)

    ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command("service neutron-lbaasv2-agent restart")
    print ssh_stdout.read()
except Exception, err:
    log.exception("Error!")

finally:
    if client:
        client.close()
