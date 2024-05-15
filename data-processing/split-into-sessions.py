import json
from datetime import datetime

PARTICIPANT = 1

INPUT = f'participant-{PARTICIPANT}_desktop-info.json'

def read_data(filename):
	"""Reads data from a JSON Lines file."""
	with open(filename, 'r') as file:
		data = [json.loads(line) for line in file]
	return data

def split_sessions(data, threshold=60):
	"""Splits data into sessions based on a time threshold."""
	sessions = []
	current_session = []
	previous_time = None

	for record in data:
		received_time = record["received_at"]
		
		if previous_time is None or received_time - previous_time <= threshold:
			current_session.append(record)
		else:
			sessions.append(current_session[:])
			current_session = [record]
		
		previous_time = received_time

	if current_session:
		sessions.append(current_session)
	
	return sessions

def save_sessions(sessions):
	"""Saves each session to a separate file."""
	for i, session in enumerate(sessions):
		output_filename = f'session_{i + 1}-{INPUT}'
		with open(output_filename, 'w') as file:
			json.dump(session, file, indent=4)

def main():
	data = read_data(INPUT)
	
	# Split data into sessions
	sessions = split_sessions(data, 60)
	
	# Save each session to a separate file
	save_sessions(sessions)

if __name__ == "__main__":
	main()