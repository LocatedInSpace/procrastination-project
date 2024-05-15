import time
import pychromecast
import zeroconf
import paho.mqtt.client as mqtt
import json
import asyncio
from pychromecast.controllers.media import MediaStatus, MediaStatusListener
from pychromecast.controllers.receiver import CastStatusListener

# ------ TOUCH THIS
NOTIFICATIONS = True # notifies the user that they shouldn't be procrastinating
RESTRICTIVE_MODE = True # stops playback
CHROMECAST_NAME = "" # the name of the chromecast device

# ------ DO NOT TOUCH BELOW THIS LINE
module = 'smarttv'
id = 'participant-6'
HIVEMQ_CLOUD_URL = ""
HIVEMQ_USERNAME = ""
HIVEMQ_PASSWORD = ''


# initialize chromecast discovery
while True:
	global chromecasts, browser
	chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[CHROMECAST_NAME])
	if len(chromecasts) > 0:
		break

chromecast = chromecasts[0]
chromecast.wait()

# Initialize MQTT client
client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=id, protocol=mqtt.MQTTv5)
client.tls_set(tls_version=mqtt.ssl.PROTOCOL_TLS)
client.username_pw_set(username=HIVEMQ_USERNAME, password=HIVEMQ_PASSWORD)

def on_connect(client, userdata, flags, reason_code, properties):
	if reason_code.is_failure:
		print(f"Failed to connect: {reason_code}. loop_forever() will retry connection")
	else:
		# Note, we subscribe to only messages directed at our module
		client.subscribe(f"{id}/{module}/#", qos=2)
client.on_connect = on_connect

def on_message(client, userdata, message):
	# we can throw away id and module, we are only subscribed to our own messages
	_, _, command = message.topic.split('/')
	# We can now act on the command
	if command == 'pong':
		print(f"Received pong from central server!")
	elif command == 'pause':
		chromecast.media_controller.pause() 
client.on_message = on_message

client.connect(HIVEMQ_CLOUD_URL, 8883)

# notify central server that this module is online
client.loop_start()
msg = client.publish(f'{module}/{id}/ping', json.dumps({
	'NOTIFICATIONS': NOTIFICATIONS,
	'RESTRICTIVE_MODE': RESTRICTIVE_MODE,
}), qos=2)
msg.wait_for_publish()

async def main():
	print("SmartTV procrastination detection started")
	while True:
		try:
			chromecast.media_controller.update_status()
		except:
			print("Chromecast disconnected")
			break
		info = {
			"playing": chromecast.media_controller.status.player_is_playing,
			"title": chromecast.media_controller.status.title,
			"current_time": chromecast.media_controller.status.current_time,
			"duration": chromecast.media_controller.status.duration,
		}
		if(info["playing"]):
			client.publish(f'{module}/{id}/info', json.dumps(info), qos=2)
			await asyncio.sleep(1)
		elif(info['title'] == None):
			await asyncio.sleep(10)
		else:
			await asyncio.sleep(2)

if __name__ == '__main__':
	loop = asyncio.get_event_loop()
	loop.run_until_complete(main())
	browser.stop_discovery()
	client.loop_stop()
	client.disconnect()

browser.stop_discovery()
client.loop_stop()
client.disconnect()