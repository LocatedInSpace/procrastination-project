from todoist_api_python.api import TodoistAPI
import asyncio
import paho.mqtt.client as mqtt
import time
import json 
from twilio.rest import Client as TwilioClient

# variables
SENSITIVITY = 10 # how many seconds of bad behaviour before we notify
TODOIST_API_TOKEN = ""
HIVEMQ_CLOUD_URL = ""
HIVEMQ_USERNAME = ""
HIVEMQ_PASSWORD = ''

TWILIO_SID = ""
TWILIO_AUTH = ""
TWILIO_NUMBER = ""
SUPERVISOR_NUMBER = ""
PHONE_NUMBER = ''

# initialize todoist api, fetch tasks
api = TodoistAPI(TODOIST_API_TOKEN)
tasks = api.get_tasks()

# initialize twilio client
tc = TwilioClient(TWILIO_SID, TWILIO_AUTH)

# hardcoded project id to participant mapping
projectid_to_name = {
	'2333116711': 'participant-1',
	'2333116715': 'participant-2',
	'2333116716': 'participant-3',
	'2333163007': 'participant-4',
	'2333163014': 'participant-5'
}
name_to_projectid = {v: k for k, v in projectid_to_name.items()}

# possible modules
modules = ['desktop', 'smarttv']

# active participants
participants = set()
participant_ifs = dict()

# history of desktop module for each participant
desktop_history = dict()
# when we sent the last notification, and why/what
desktop_activity = dict()
# how active the participant is on desktop (keyboard, mouse)
desktop_activity_level = dict()
activity_delta = 15 # seconds
activity_amount = 6 # how many activity to average
activity_timespan_check = 600 # seconds, 10 minutes
percentage_warning = 0.20 # if the last activity_amount averages to less than this compared to activity_timespan_check, we send a warning

# history of smarttv module for each participant
smarttv_history = dict()
# when we sent the last notification, and why/what
smarttv_activity = dict()
# the configuration for this user, NOTIFICATIONS and RESTRICTIVE_MODE
smarttv_config = dict()

# Initialize MQTT client
# This is where we will publish and subscribe to messages.
client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id='central', protocol=mqtt.MQTTv5)
client.tls_set(tls_version=mqtt.ssl.PROTOCOL_TLS)
client.username_pw_set(username=HIVEMQ_USERNAME, password=HIVEMQ_PASSWORD)

def on_subscribe(client, userdata, mid, reason_code_list, properties):
	# Since we subscribed only for a single channel, reason_code_list contains
	# a single entry
	if reason_code_list[0].is_failure:
		print(f"Broker rejected you subscription: {reason_code_list[0]}")
	else:
		print(f"Broker granted the following QoS: {reason_code_list[0].value}")
client.on_subscribe = on_subscribe

def on_message(client, userdata, message):
	global activity_delta, activity_amount, activity_timespan_check, percentage_warning, tasks
	global supervisor, dc
	# userdata is the structure we choose to provide, here it's a list()
	userdata.append(message.payload)
	# if this is sent to a participant, we ignore it
	if message.topic.startswith('participant'):
		return
	
	#print(f"Received message '{message.payload}' on topic '{message.topic}'")
	module, id, command = message.topic.split('/')
	if module not in modules:
		print(f"Unknown module: {module}")
		return
	participants.add(id)

	if command == 'ping':
		tasks = api.get_tasks()
		print(f"Received ping from {module}/{id}")
		if module == 'desktop':
			pong(client, module, id)
			update_commitments(client, module, id)
			update_tasks(client, module, id)
		elif module == 'smarttv':
			# update smarttv config
			data = json.loads(message.payload.decode())
			smarttv_config[id] = data
	elif command == 'info':
		if module == 'desktop':
			info_desktop(client, id, message.payload.decode())
		elif module == 'smarttv':
			info_smarttv(client, id, message.payload.decode())
	elif command == 'activity':
		if module == 'desktop':
			raw = message.payload.decode()
			if id not in desktop_activity_level:
				desktop_activity_level[id] = []
			data = json.loads(raw)
			now = time.time()
			data['received_at'] = now
			desktop_activity_level[id].append(data) # has 'keys' and 'mouse'
			log_to_file(id, 'desktop-activity', data)
			if len(desktop_activity_level[id])*activity_delta >= activity_timespan_check:
				# we have enough data to check
				
				# calculate the recent average activity
				activity = desktop_activity_level[id][-activity_amount:]
				recent_average_activity = sum([(a['keys'] * 2) + a['mouse'] for a in activity])

				# calculate average activity preceding the last activity_timespan_check
				old_activity = desktop_activity_level[id][-(activity_timespan_check // activity_delta):-activity_amount]
				old_average_activity = sum([(a['keys'] * 2) + a['mouse'] for a in old_activity])
				if(old_average_activity == 0):
					# we don't want to divide by zero
					return
				# calculate how much percentagewise the recent activity is compared to the old activity
				average_activity = recent_average_activity / old_average_activity
				if average_activity <= percentage_warning:
					# warn the user, only if the last 15 of 25 was work/unknown
					# makes no sense to warn if the user is already procrastinating
					if(len(desktop_history[id]) < 25):
						return
					last_25 = desktop_history[id][-25:]
					count = 0
					for i in range(25):
						if last_25[i]['procrastination_type'] in ['work', 'unknown']:
							count += 1
					if count < 15:
						# makes no sense to warn for productivity if the user is already procrastinating
						return
					client.publish(f'{id}/{module}/activity', "Your productivity seems to be dropping, you can do it! :)", qos=2)
					log_to_file(id, 'desktop-activity_warn', {'sent_at': now, 'message': "Your productivity seems to be dropping, you can do it! :)", 'average_activity': average_activity})
					# clear the desktop activity level, so we dont sent repeated warnings for especially productive periods
					desktop_activity_level[id] = []
	elif command == 'notifysupervisor':
		if module == 'desktop':
			msg = message.payload.decode()
			msg = f'{id}: {msg}'
			# notify supervisor
			tc.messages.create(to=SUPERVISOR_NUMBER, from_=TWILIO_NUMBER, body=msg)
	else:
		print(f"Unknown command: {command}")

client.on_message = on_message

def on_connect(client, userdata, flags, reason_code, properties):
	if reason_code.is_failure:
		print(f"Failed to connect: {reason_code}. loop_forever() will retry connection")
	else:
		# Note, that since we are the central server, we will subscribe to everything
		client.subscribe("#", qos=2)
client.on_connect = on_connect


client.user_data_set(list())
client.connect(HIVEMQ_CLOUD_URL, 8883)

client.loop_start()
### --- Commands --- ###
def pong(client, module, id):
	# notify module that central server is online
	client.publish(f'{id}/{module}/pong', f'Hello {id}!', qos=2)
	# reset the history for the participants
	if module == 'desktop':
		global desktop_activity_level, desktop_history, desktop_activity
		desktop_history[id] = []
		desktop_activity[id] = []
		desktop_activity_level[id] = []


def notification(client, module, id, message):
	# notify module that central server is online
	client.publish(f'{id}/{module}/notification', f'{message}', qos=2)

def update_commitments(client, module, id):
	global tasks
	project_id = ""
	try:
		project_id = name_to_projectid[id]
	except KeyError:
		print(f"Unknown participant id: {id}")
		return
	commitments = []
	for task in tasks:
		if task.project_id == project_id and task.content == 'Commitments':
			description = task.description.split('\n')
			for line in description:
				if line.startswith('Commitment: '):
					commitments.append(line[12:])
	# send the commitments to the module
	client.publish(f'{id}/{module}/commitments', json.dumps(commitments), qos=2)

def update_tasks(client, module, id):
	global tasks, if_tasks, participant_ifs
	project_id = ""
	try:
		project_id = name_to_projectid[id]
	except KeyError:
		print(f"Unknown participant id: {id}")
		return
	participant_ifs[id] = []
	project_tasks = []
	if_tasks = []
	for task in tasks:
		if task.project_id == project_id and task.content != 'Commitments' and not task.content.startswith('//'):
			if task.content.startswith('if ') and " then " in task.content:
				if_tasks.append(task)
			else:
				project_tasks.append(task)
	for task in if_tasks:
		parts = task.content.split(' ')
		# if x minutes y then (z ...)
		participant_ifs[id].append({
			'minutes': parts[1],
			'seconds_left': int(parts[1]) * 60,
			'type': parts[3],
			'promise': ' '.join(parts[5:]),
			'id': task.id,
			'original': task.content
		})
	# send the task name to the module, but only the first one
	if len(project_tasks) > 0:
		client.publish(f'{id}/{module}/task', project_tasks[0].content, qos=2)
	

def info_desktop(client, id, data):
	data = json.loads(data)
	global desktop_history, desktop_activity
	now = time.time()
	data['received_at'] = now
	message = {
		'type': data['procrastination_type'],
		'wandering_time': data['wandering_time'],
		'working_time': data['working_time'],
		'procrastination_time': data['procrastination_time'],
		'idx': data['idx'],
		'level': 0
	}
	# data is a dictionary with keys: 'wandering_time', 'working_time', 'procrastination_type', and 'idx' (index of the last visited window)
	# ... and 'received_at' that we added
	# we store this for later analysis
	if id not in desktop_history:
		desktop_history[id] = []
	desktop_history[id].append(data)
	log_to_file(id, 'desktop-info', data)

	if data['procrastination_type'] in ['work', 'unknown']:
		# we don't want to send notifications for these
		return
	
	# check if they have any ifs for this type of procrastination
	ifs_to_remove = []
	if id in participant_ifs:
		for i in range(len(participant_ifs[id])):
			if participant_ifs[id][i]['type'] == data['procrastination_type']:
				participant_ifs[id][i]['seconds_left'] -= 1
				if participant_ifs[id][i]['seconds_left'] <= 0:
					# send notification that they're if is done, and what they promised
					api.update_task(participant_ifs[id][i]['id'], content=f"// {participant_ifs[id][i]['original']}")
					msg = f"Your {participant_ifs[id][i]['minutes']} minutes of {participant_ifs[id][i]['type']} is done!\nThis leaves, '{participant_ifs[id][i]['promise']}'"
					client.publish(f'{id}/desktop/if', msg, qos=2)
					ifs_to_remove.append(i)
					log_to_file(id, 'desktop-ifthen', {'sent_at': now, 'if': participant_ifs[id][i], 'message': msg})
				else:
					# dont send notifications, since they're still in the if
					return
	removed = 0
	for i in ifs_to_remove:
		del participant_ifs[id][i - removed]
		removed += 1

	
	# make sure it is greater than the sensitivity
	if data['procrastination_time'] <= SENSITIVITY:
		return
	
	if id not in desktop_activity:
		desktop_activity[id] = []
	# first we check the activity of us, to see if we've recently sent a notification
	if len(desktop_activity[id]) > 0:
		last_notification = desktop_activity[id][-1]
		# last notification has ['sent_at', 'reason', 'message']
		if now - last_notification['sent_at'] < 60:
			# we've sent a notification in the last minute, we don't want to spam the user
			return
		# now we check if we recently sent a notification because of the same reason
		if now - last_notification['sent_at'] < 600 and last_notification['reason'] == data['procrastination_type']:
			# we've sent a notification in the last 10 minutes, and it was because of the same reason
			# we therefore want to send the next level of notification
			message['level'] = last_notification['message']['level'] + 1
	else:
		# we haven't sent any notifications yet
		message['idx'] = data['idx']
	# now we send the notification
	notification(client, 'desktop', id, json.dumps(message))
	desktop_activity[id].append({'sent_at': now, 'reason': data['procrastination_type'], 'message': message})
	log_to_file(id, 'desktop-notifications', {'sent_at': now, 'reason': data['procrastination_type'], 'message': message})


def info_smarttv(client, id, data):
	global smarttv_history, smarttv_activity, smarttv_config, tc
	data = json.loads(data)
	now = time.time()
	data['received_at'] = now
	# data is a dictionary with keys: 'playing', 'title', 'current_time', 'duration'
	# ... and 'received_at' that we added
	# we store this for later analysis
	if id not in smarttv_history:
		smarttv_history[id] = []
	smarttv_history[id].append(data)
	log_to_file(id, 'smarttv-info', data)
	if data['playing']:
		# check if we should notify the user
		if id not in smarttv_activity:
			smarttv_activity[id] = []
		# first we check the activity of us, to see if we've recently sent a notification
		if len(smarttv_activity[id]) > 0:
			last_notification = smarttv_activity[id][-1]
			# last notification has ['sent_at', 'message']
			if now - last_notification['sent_at'] > 60 and smarttv_config[id]['NOTIFICATIONS']:
				time_left = data['duration'] - data['current_time']
				msg = f"Are you really watching {data['title']} for {time_left} more seconds?"
				tc.messages.create(to=SUPERVISOR_NUMBER, from_=TWILIO_NUMBER, body=msg)
				smarttv_activity[id].append({'sent_at': now, 'message': msg})
			if now - last_notification['sent_at'] > 5 and smarttv_config[id]['RESTRICTIVE_MODE']:
				# tell the smarttv to stop playing
				client.publish(f'{id}/smarttv/pause', "", qos=2)
				msg = f"Stop watching {data['title']}"
				tc.messages.create(to=SUPERVISOR_NUMBER, from_=TWILIO_NUMBER, body=msg)
				smarttv_activity[id].append({'sent_at': now, 'message': msg})
		else:
			smarttv_activity[id].append({'sent_at': now - 60, 'message': '---'})


def log_to_file(id, module, data):
	with open(f'{id}_{module}.json', 'a') as f:
		f.write(json.dumps(data))
		f.write('\n')

async def main():
	while True:
		await asyncio.sleep(0.25)

if __name__ ==  '__main__':
	loop = asyncio.get_event_loop()
	loop.run_until_complete(main())
	client.loop_stop()
