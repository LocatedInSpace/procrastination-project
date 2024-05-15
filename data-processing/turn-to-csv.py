import json
import csv

PARTICIPANT = 1
SESSION = 2
DESCRIPTOR = 'desktop-info'
LABEL_NOTIFICATIONS = True
NOTIFICATION_LABEL = ''

INPUT = f'session_{SESSION}-participant-{PARTICIPANT}_{DESCRIPTOR}'
OUTPUT = f'participant-{PARTICIPANT}_session-{SESSION}'
NOTIFICATION_FILE = f'participant-{PARTICIPANT}_desktop-notifications.json'

def read_data(filename):
		"""Reads data from a JSON file."""
		with open(filename, 'r') as file:
				data = json.load(file)
		return data

def read_notif_data(filename, session_data):
	"""Reads data from a JSON Lines file."""
	with open(filename, 'r') as file:
		data = [json.loads(line) for line in file]
	# get the start time of the session
	start_time = session_data[0]['received_at']
	# get the end time of the session
	end_time = session_data[-1]['received_at']
	# filter notifications that are within the session
	notifications = [record for record in data if start_time <= record['sent_at'] <= end_time]
	for n in notifications:
		n['sent_at'] = n['sent_at'] - start_time
	return notifications

def process_data(data):
		"""Processes the data to calculate elapsed time and format it for CSV."""
		processed_data = []
		start_time = data[0]['received_at']

		for record in data:
				elapsed_time = record['received_at'] - start_time
				# round the elapsed time to 2 decimal places
				elapsed_time = round(elapsed_time, 2)
				processed_record = [
						elapsed_time,
						record['working_time'],
						record['procrastination_time'],
						record['wandering_time']
				]
				processed_data.append(processed_record)

		return processed_data

def process_data_stacked(data):
		"""Instead of resetting working_time, procrastination_time, and wandering_time to 0, stack them."""
		processed_data = []
		start_time = data[0]['received_at']
		working_time = 0
		procrastination_time = 0
		wandering_time = 0

		last_working_time = 0
		last_procrastination_time = 0
		last_wandering_time = 0

		for record in data:
				elapsed_time = record['received_at'] - start_time
				# round the elapsed time to 2 decimal places
				elapsed_time = round(elapsed_time, 2)
				#working_time += 0 if record['working_time'] - last_working_time == 0 else 1
				#procrastination_time += 0 if record['procrastination_time'] - last_procrastination_time == 0 else 1
				#wandering_time += 0 if record['wandering_time'] - last_wandering_time == 0 else 1

				working_time += 0 if record['working_time'] - last_working_time <= 0 else (record['working_time'] - last_working_time)
				procrastination_time += 0 if record['procrastination_time'] - last_procrastination_time <= 0 else (record['procrastination_time'] - last_procrastination_time)
				wandering_time += 0 if record['wandering_time'] - last_wandering_time <= 0 else (record['wandering_time'] - last_wandering_time)

				last_working_time = record['working_time']
				last_procrastination_time = record['procrastination_time']
				last_wandering_time = record['wandering_time']

				processed_record = [
						elapsed_time,
						working_time,
						procrastination_time,
						wandering_time
				]
				processed_data.append(processed_record)

		return processed_data

def save_to_csv(processed_data, output_filename, notification_data=None):
		"""Saves the processed data to a CSV file."""
		headers = ["Elapsed Time", "Working Time", "Procrastination Time", "Wandering Time"]
		if LABEL_NOTIFICATIONS:
			headers.append("Notification")
			# add to processed_data the notification data
			for record in processed_data:
				# get the time of the record
				time = record[0]
				try:
					if notification_data[0]['sent_at'] <= time:
						record.append(f"{NOTIFICATION_LABEL}{notification_data[0]['reason']}, L{notification_data[0]['message']['level']}")
						notification_data = notification_data[1:]
					else:
						record.append('')
				except IndexError:
					record.append('')
		with open(output_filename, 'w', newline='') as file:
			writer = csv.writer(file, delimiter=';')
			writer.writerow(headers)
			writer.writerows(processed_data)

def main():
		# Read data from file
		input_filename = f'{INPUT}.json'
		output_filename = f'{INPUT}.csv'
		data = read_data(input_filename)

		if (LABEL_NOTIFICATIONS):
				notification_data = read_notif_data(NOTIFICATION_FILE, data)
		else:
				notification_data = None
		# Process the data
		processed_data = process_data(data)
		processed_data_stacked = process_data_stacked(data)

		# Save the processed data to a CSV file
		output1_filename = f'{OUTPUT}_raw.csv'
		output2_filename = f'{OUTPUT}_stacked.csv'
		save_to_csv(processed_data, output1_filename, notification_data)
		save_to_csv(processed_data_stacked, output2_filename, notification_data)

if __name__ == "__main__":
		main()