import paho.mqtt.client as mqtt
from win11toast import notify
import json
import asyncio
from win32gui import GetWindowText, GetForegroundWindow
import random
from pynput import keyboard, mouse

# ------ TOUCH THIS
NOTIFICATIONS = True
PRODUCTIVITY_MEASUREMENT = True


# ------ DO NOT TOUCH BELOW THIS LINE
module = 'desktop'
id = 'participant-1'
HIVEMQ_CLOUD_URL = ""
HIVEMQ_USERNAME = ""
HIVEMQ_PASSWORD = ''

# customization - only enable one!
positive_feedback_enabled = True
negative_feedback_enabled = False
public_feedback_enabled = False # hardcoded to notify me!

# Initialize MQTT client
client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=id, protocol=mqtt.MQTTv5)
client.tls_set(tls_version=mqtt.ssl.PROTOCOL_TLS)
client.username_pw_set(username=HIVEMQ_USERNAME, password=HIVEMQ_PASSWORD)

# For debug purposes
#def on_log(client, userdata, paho_log_level, message):
#  print(message)
#client.on_log = on_log

def on_connect(client, userdata, flags, reason_code, properties):
	if reason_code.is_failure:
		print(f"Failed to connect: {reason_code}. loop_forever() will retry connection")
	else:
		# Note, we subscribe to only messages directed at our module
		client.subscribe(f"{id}/{module}/#", qos=2)
client.on_connect = on_connect

def on_message(client, userdata, message):
	#print(f"Received message '{message.payload}' on topic '{message.topic}'")
	# we can throw away id and module, we are only subscribed to our own messages
	_, _, command = message.topic.split('/')
	# We can now act on the command
	if command == 'pong':
		print(f"Received pong from central server!")
	elif command == 'commitments':
		global commitments
		commitments = json.loads(message.payload.decode())
	elif command == 'notification':
		msg = message.payload.decode()
		generated_notification = generate_notification(json.loads(msg))
		if generated_notification == '':
			return
		if(NOTIFICATIONS):
			notify(generated_notification, scenario='incomingCall')
		else:
			print(f"Received notification: {generated_notification}")
	elif command == 'activity': # this is only used for when the central server isn't seeing enough activity
		msg = message.payload.decode()
		if(NOTIFICATIONS and PRODUCTIVITY_MEASUREMENT):
			notify(msg, scenario='incomingCall', audio={'silent': 'true'})
		else:
			print(f"Received notification: {msg}")
	elif command == 'if':
		msg = message.payload.decode()
		if(NOTIFICATIONS):
			notify(msg, scenario='incomingCall', audio={'silent': 'true'})
		else:
			print(f"Received notification: {msg}")
	elif command == 'task':
		global task_name
		task_name = message.payload.decode()
		print(f"Received task name: {task_name}")
client.on_message = on_message

client.connect(HIVEMQ_CLOUD_URL, 8883)

# notify central server that this module is online
client.loop_start()
msg = client.publish(f'{module}/{id}/ping', f'Hello server!', qos=2)
msg.wait_for_publish()

# -------------- global values set by central server
task_name = ''
commitments = []

# -------------- global values set by this module
wandering_time = 0 # how long a user is allowed to do other stuff before we intervene
working_time = 0 # how long a user has worked continously in seconds
procrastination_time = 0 # how long a user has procrastinated in seconds

last_visited_windows = [()] # list of last visited windows

seconds_till_check_work = 0
work_seconds_required = 0
work_seconds_done = 0

keys_pressed = 0 # how many keys have been pressed since last check
mouse_events = 0 # how many mouse events have been registered since last check

# --------- DESKTOP PROCRASTINATION DETECTION

# -- keyboard listener
def on_press(key):
	global keys_pressed
	keys_pressed += 1
		
klistener = keyboard.Listener(
	on_press=on_press,
	on_release=None)
klistener.start()

# -- mouse listener
def on_move(x, y):
	global mouse_events
	mouse_events += 1/100

def on_click(x, y, button, pressed):
	global mouse_events
	mouse_events += 1

def on_scroll(x, y, dx, dy):
	global mouse_events
	mouse_events += 1

mlistener = mouse.Listener(
	on_move=on_move,
	on_click=on_click,
	on_scroll=on_scroll)
mlistener.start()

def generate_notification(message): 
	global last_visited_windows, work_seconds_required, seconds_till_check_work
	global commitments, positive_feedback_enabled, negative_feedback_enabled, public_feedback_enabled
	global task_name
	# message is 'type', 'wandering_time', 'working_time', 'procrastination_time', 'idx', and 'level'
	window = last_visited_windows[message['idx']]
	level = message['level']
	msg = ""
	type = message['type']
	if positive_feedback_enabled:
		if type == 'work':
			pass # no feedback, but in theory we could
		elif type == 'video':
			if level == 0:
				msg = "You still have work to do, *1 can wait! :)"
			elif level == 1:
				msg = f"*1 will still be there later, didn't you say that you wanted to: {random.choice(commitments)}!"
			elif level == 2:
				msg = "You have been watching *1 for a while now, it's time to get back to work."
			elif level == 3:
				msg = "You are procrastinating, no more *1!"
			else:
				msg = f"You've been on *1 for {level} minutes, you can still make good progress with work!"
		elif type == 'messaging':
			if level == 0:
				msg = "You still have work to do, *1 can wait! :)"
			elif level == 1:
				msg = f"*1 will still be there later, didn't you say that you wanted to: {random.choice(commitments)}!"
			elif level == 2:
				msg = "You have been messaging on *1 for a while now, it's time to get back to work."
			elif level == 3:
				msg = "You are procrastinating, no more *1!"
			else:
				msg = f"You've been on *1 for {level} minutes, you can still make good progress with work!"
		elif type == 'scrolling':
			if level == 0:
				msg = "Do you really want to be scrolling *1 right now? :)"
			elif level == 1:
				msg = f"Remember that you wanted to: {random.choice(commitments)} instead of scrolling *1!"
			elif level == 2:
				msg = "You have been scrolling *1 for a while now, it's time to get back to work."
			elif level == 3:
				msg = "You are procrastinating, no more *1!"
			else:
				msg = f"You've been on *1 for {level} minutes, you can still make good progress with work!"
		elif type == 'games':
			if level == 0:
				msg = "Do you really want to be playing *1 right now? It's not too late to quit out :)"
			elif level == 1:
				msg = f"Remember that you wanted to: {random.choice(commitments)} instead of playing *1!"
			elif level == 2:
				msg = "You have been playing *1 for a while now, it's time to get back to work."
			elif level == 3:
				msg = "You are procrastinating, no more *1!"
			else:
				msg = f"You've been on *1 for {level} minutes, you can still make good progress with work!"
	elif negative_feedback_enabled:
		if level == 0:
			msg = "You aren't being very productive right now, are you?"
		elif level == 1:
			msg = f"What happened to {random.choice(commitments)} - was that fake?"
		elif level == 2:
			msg = "You will not get your work done at this rate. *1 over your future?"
		else:
			msg = f"{level} minutes wasted on *1, you will not complete the task in time at this rate."
	elif public_feedback_enabled:
		if (work_seconds_required > 0) and (work_seconds_required - work_seconds_done) <= 0:
			pass # since they've done the required work, no need to notify
		elif level == 0:
			if(work_seconds_required == 0):
				msg = "It seems like *1 is more important than work right now. You have 30 minutes to do at least 10 minutes of work or I will notify your supervisor."
				work_seconds_required = 10 * 60
				seconds_till_check_work = 30 * 60
			else:
				msg = f"Still not working? You have {seconds_till_check_work / 60} minutes left to do at least {(work_seconds_required - work_seconds_done) / 60} minutes of work."
		elif level == 1:
			if work_seconds_required == 10 * 60:
				msg = f"It seems 10 minutes of work was not scary enough. You have {seconds_till_check_work / 60} minutes to do at least 15 minutes of work or I will notify your supervisor."
				work_seconds_required = 15 * 60
			else: 
				msg = f"Still not working? You have {seconds_till_check_work / 60} minutes left to do at least {(work_seconds_required - work_seconds_done) / 60} minutes of work."
		elif level == 2:
			if work_seconds_required == 15 * 60:
				msg = f"You have {seconds_till_check_work / 60} minutes to do at least 20 minutes of work or I will notify your supervisor."
				work_seconds_required = 20 * 60
			else: 
				msg = f"Next warning will require no break. You have {seconds_till_check_work / 60} minutes left to do at least {(work_seconds_required - work_seconds_done) / 60} minutes of work."
		else:
			msg = f"You are running out of time. You have {seconds_till_check_work / 60} minutes left to do at least {(work_seconds_required - work_seconds_done) / 60} minutes of work."
	if task_name != '':
		msg = f"Active task: {task_name}\n {msg}"
	msg = msg.replace('*1', window[2])
	return msg

# takes a title of a window, and returns true or false on how likely it is to be procrastination
# it will also return the type of procrastination
def is_this_procrastination(title):
	global last_visited_windows
	# known dedicated video sites/titles, others may also be video sites
	video = set([
		'YouTube', 'Netflix', 'HBO', 'Disney', 'Prime Video', 'TikTok', 'Twitch', '.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv'
	])
	# known dedicated messaging sites/titles
	messaging = set([
		'WhatsApp', 'Messenger', 'Snapchat', 'Discord', 'Telegram'
	])
	# known dedicated browsing/scrolling sites/titles
	scrolling = set([
		'Facebook', 'Twitter', 'Reddit', 'Instagram', 'Tumblr', '9gag', 'Buzzfeed', '/ X'
	])
	# if these are in the title, together with a procrastination site, it may indicate procrastination is about to occur
	warning = set([
		'Google Search', 'at DuckDuckGo',
	])
	# titles that are likely to be work related
	work = set([
		'Visual Studio Code', 'Stack Overflow', 'GitHub', 'Photoshop', 'Gmail', 'Mail', 'Overleaf'
		'Word', 'Excel', 'PowerPoint', 'Outlook', 'Teams', 'OneNote', 'SharePoint', 'OneDrive', 'Access', 'Publisher',
		'Slack', 'Zoom', 'Wikipedia', 'Google Scholar', 'Google Docs', 'Google Sheets', 'Google Slides', 'Google Drive',
		'Jira', 'Confluence', 'Trello', 'Asana', 'Notion', 'Issue #', 'Pull Request', 'Merge Request', 'Code Review',
		'The Guardian', 'The Washington Post', 'The Wall Street Journal', 'The Economist', 'The Atlantic', 'Indeed.com'
	])
	# titles that are probably games
	games = set([
		'Steam', 'Epic Games', 'Origin', 'Uplay', 'Battle.net', 'GOG.com', 'itch.io', 'Humble Bundle', 'Game Jolt', 'GameMaker Studio',
		'Minecraft', 'Fortnite', 'League of Legends', 'World of Warcraft', 'Overwatch', 'Hearthstone', 'Diablo', 'Starcraft', 'Heroes of the Storm',
		'Call of Duty', 'Warcraft', 'Halo', 'Destiny', 'Apex Legends', 'Valorant', 'Counter-Strike', 'Dota', 'Team Fortress', 'Half-Life', 'Portal',
		'CS:GO', 'CS2', 'DirectX', 'OpenGL', 'Friends List', 'Osu!', 'Ultrakill'
	])

	idx = len(last_visited_windows)

	if any(x.lower() in title.lower() for x in work):
		# find out what matched
		candidate = [x for x in work if x.lower() in title.lower()][0]
		last_visited_windows.append((title, 'work', candidate))
		return False, 'work', idx
	elif any(x.lower() in title.lower() for x in video):
		# find out what matched
		candidate = [x for x in video if x.lower() in title.lower()][0]
		# check if in warning
		if any(x.lower() in title.lower() for x in warning):
			last_visited_windows.append((title, 'video likely', candidate))
			return False, 'video likely', idx
		last_visited_windows.append((title, 'video', candidate))
		return True, 'video', idx
	elif any(x.lower() in title.lower() for x in messaging):
		# find out what matched
		candidate = [x for x in messaging if x.lower() in title.lower()][0]
		# check if in warning
		if any(x.lower() in title.lower() for x in warning):
			last_visited_windows.append((title, 'messaging likely', candidate))
			return False, 'messaging likely', idx
		last_visited_windows.append((title, 'messaging', candidate))
		return True, 'messaging', idx
	elif any(x.lower() in title.lower() for x in scrolling):
		# find out what matched
		candidate = [x for x in scrolling if x.lower() in title.lower()][0]
		# check if in warning
		if any(x.lower() in title.lower() for x in warning):
			last_visited_windows.append((title, 'scrolling likely', candidate))
			return False, 'scrolling likely', idx
		last_visited_windows.append((title, 'scrolling', candidate))
		return True, 'scrolling', idx
	elif(any(x.lower() in title.lower() for x in games)):
		# find out what matched
		candidate = [x for x in games if x.lower() in title.lower()][0]
		# check if in warning
		if any(x.lower() in title.lower() for x in warning):
			last_visited_windows.append((title, 'games likely', candidate))
			return False, 'games likely', idx
		last_visited_windows.append((title, 'games', candidate))
		return True, 'games', idx
	else:
		last_visited_windows.append((title, 'unknown', ''))
		return False, 'unknown', idx


async def main():
	global wandering_time, working_time, procrastination_time
	global seconds_till_check_work, work_seconds_required, work_seconds_done
	global mouse_events, keys_pressed
	delay = 1
	MOUSE_KEY_DELTA = 15 # how many seconds we accumulate for key/mouse events
	counter = 0

	print("Procrastination detection started")

	while True:
		title = GetWindowText(GetForegroundWindow())
		procrastination, procrastination_type, idx = is_this_procrastination(title)
		print(f"Title: {title}, procrastination: {procrastination}, type: {procrastination_type}")
		if 'likely' in procrastination_type:
			wandering_time += delay
			working_time = 0
		elif procrastination:
			procrastination_time += delay
			procrastination_time += wandering_time
			wandering_time = 0
			working_time = 0
		else:
			work_seconds_done += delay
			working_time += delay
			if procrastination_type == 'work':
				# only reset if we are certain they are working
				wandering_time = 0
				procrastination_time = 0
		#print(f"Working time: {working_time}, Procrastination time: {procrastination_time}, Wandering time: {wandering_time}")
		
		# send the working time, procrastination time and wandering time to the central server, as well as the type of procrastination
		# this will allow the central server to make a decision on what to do
		# the central server will then send a command back to the module with instructions, asynchronously from this loop
		info = {
			'working_time': working_time,
			'procrastination_time': procrastination_time,
			'wandering_time': wandering_time,
			'procrastination_type': procrastination_type,
			'idx': idx
		}
		client.publish(f'{module}/{id}/info', json.dumps(info), qos=2)

		if seconds_till_check_work > 0:
			seconds_till_check_work -= delay
			if seconds_till_check_work <= 0:
				if work_seconds_done < work_seconds_required:
					print("Notifying supervisor")
					if(NOTIFICATIONS):
						client.publish(f'{module}/{id}/notifysupervisor', f'User has not done enough work, only {work_seconds_done / 60} minutes of work in the last 30 minutes. They were meant to do {work_seconds_required / 60} minutes.', qos=2)
				seconds_till_check_work = 0
				work_seconds_required = 0
				work_seconds_done = 0
		
		counter += 1
		if counter >= MOUSE_KEY_DELTA:
			# send to central server
			client.publish(f'{module}/{id}/activity', json.dumps({
				'keys': keys_pressed,
				'mouse': mouse_events
			}), qos=2)
			keys_pressed = 0
			mouse_events = 0
			counter = 0
		
		await asyncio.sleep(delay)

if __name__ == '__main__':
	loop = asyncio.get_event_loop()
	loop.run_until_complete(main())
	client.loop_stop()
	client.disconnect()

client.loop_stop()
client.disconnect()