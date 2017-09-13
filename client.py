from oslo_config import cfg
import oslo_messaging as messaging
import logging

logging.basicConfig()
log = logging.getLogger()

log.addHandler(logging.StreamHandler())
log.setLevel(logging.INFO)

transport_url = 'rabbit://openstack:123456@10.76.0.2:5672/'
transport = messaging.get_transport(cfg.CONF, transport_url)

driver = 'messaging'

notifier = messaging.Notifier(transport, driver=driver, publisher_id='testing',topics="test")
notifier.info({'some': 'context'}, 'just.testing', {'heavy': 'payload'})