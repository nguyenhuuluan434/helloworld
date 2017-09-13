#!/usr/bin/python

import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.sql import text

import paramiko
import ConfigParser

from keystoneauth1.identity import v3
from keystoneauth1 import session
from neutronclient.v2_0 import client as neutronclient

if (len(sys.argv) < 3):
    print "Need 2 pram: host_dead host_backup";
    exit(0);

Config = ConfigParser.ConfigParser()
if not os.path.isfile("config.ini"):
    print "File config config.ini not exist \n"
    exit(0)
else:
    Config.read("config.ini")


def ConfigSectionMap(section):
    dict = {}
    options = Config.options(section)
    for option in options:
        try:
            dict[option] = Config.get(section, option)
        except:
            dict[option] = None
    return dict


print "host_dead: " + sys.argv[1];
print "host_backup: " + sys.argv[2] + "\n";

engine = create_engine('mysql://hacompute:123456@10.76.0.2:3306')
connection = engine.connect()

# '''connect to OPS'''

options_ops = ConfigSectionMap("config_ops")

auth = v3.Password(auth_url=options_ops['os_auth_url'],
                   username=options_ops['os_username'],
                   password=options_ops['os_password'],
                   project_name=options_ops['os_project_name'],
                   user_domain_id=options_ops['os_user_domain_id'],
                   project_domain_id=options_ops['os_project_domain_id'])

sess = session.Session(auth=auth)
neutron = neutronclient.Client(session=sess)

agents = neutron.list_agents()["agents"];

lb_agents = {}

for agent in agents:
    if agent['binary'] == 'neutron-lbaasv2-agent':
        lb_agents[agent['host']] = agent['id'];
print lb_agents
print "\n"

if False == lb_agents.has_key(sys.argv[1]):
    print "host_dead wrong";
    exit(0);

if False == lb_agents.has_key(sys.argv[2]):
    print "host_backup wrong";
    exit(0);

lb_failed = []
sqlQuerySelect = "SELECT * FROM neutron.lbaas_loadbalanceragentbindings;";
agentbindings = connection.execute(text(sqlQuerySelect)).fetchall();

for row in agentbindings:
    if str(row[1]).__contains__(lb_agents.get(str(sys.argv[1]))) and str(row[1]).__eq__(
            lb_agents.get(str(sys.argv[1]))):
        lb_failed.append(row[0])

sqlQueryUpdate = 'UPDATE neutron.lbaas_loadbalanceragentbindings' \
           ' SET neutron.lbaas_loadbalanceragentbindings.agent_id = \"%s\" ' \
           ' WHERE neutron.lbaas_loadbalanceragentbindings.agent_id = \"%s\" ' \
           ' AND neutron.lbaas_loadbalanceragentbindings.loadbalancer_id = \"%s\" ;'

for lb in lb_failed:
    cmd = sqlQueryUpdate % (lb_agents.get(str(sys.argv[2])), lb_agents.get(str(sys.argv[1])), lb);
    print cmd
    resources = connection.execute(text(cmd))

# restart loadbalancer agent on backup host
try:
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    key = paramiko.RSAKey.from_private_key_file("/root/.ssh/id_rsa")
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print('*** Connecting to %s...***' % sys.argv[2])
    client.connect(sys.argv[2], username="root", pkey=key)

    ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command("service neutron-lbaasv2-agent restart")
    print ssh_stdout.read()

finally:
    if client:
        client.close()
