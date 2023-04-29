import serial.tools.list_ports
import json
from threading import Lock
from flask import Flask, render_template, session, request, jsonify, url_for
from flask_socketio import SocketIO, emit, disconnect    
import serial
import re
import mysql.connector


ports = serial.tools.list_ports.comports()

for port, desc, hwid in sorted(ports):
    print("{}: {} [{}]".format(port, desc, hwid))


async_mode = None
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode=async_mode)
thread = None
thread_lock = Lock() 



def save_to_db(data):
    try:
        cnx = mysql.connector.connect(**config)
        cursor = cnx.cursor()

        query = "INSERT INTO distance_table (value) VALUES (%s)"
        data_str = json.dumps(data)
        value = (data_str,)

        cursor.execute(query, value)
        cnx.commit()

        print(f"Successfully inserted {data} into distance_table")
    except mysql.connector.Error as error:
        print(f"Error inserting {data} into distance_table: {error}")
    finally:
        if cnx.is_connected():
            cursor.close()
            cnx.close()

def read_from_db():
    try:
        cnx = mysql.connector.connect(**config)
        cursor = cnx.cursor()

        query = "SELECT value FROM distance_table"
        cursor.execute(query)

        results = []
        for row in cursor.fetchall():
            results.append(row[0])

        return results
    except mysql.connector.Error as error:
        print(f"Error reading from distance_table: {error}")
    finally:
        if cnx.is_connected():
           cursor.close()
           cnx.close()


def save_to_file(data, filename):
    try:
        with open(filename, 'a') as f:
            f.write(json.dumps(data) + '\n')

        print(f"Successfully saved data to {filename}")
    except IOError as e:
        print(f"Error saving data to {filename}: {e}")

def read_from_file(filename):
    try:
        with open(filename, 'r') as f:
            data = f.read().splitlines()
        print(f"Successfully read data from {filename}")
        return data
    except IOError as e:
        print(f"Error reading data from {filename}: {e}")
        return None

def background_thread(args):
    last = ""
    data = ""
    count = 0
    arduino = serial.Serial('COM11', baudrate=9600, timeout=1)
    while True:
        received_message = arduino.readline().decode('utf-8');
        data_list = []
        print(received_message)
        if(received_message):
            count = count + 1
            try:
                data = json.loads(received_message)
                data_list.append(data)
                print(data)
                save_to_db(data)
                save_to_file(data, "output_data")
                json_object = read_from_file("output_data")
                socketio.emit('my_response', {'data': json_object[-1], 'count': count }, namespace='/test')
            except json.JSONDecodeError:
                pass
        if args:
            action = dict(args).get('btn_value')
            if(action and action != last):
                print(args)
                arduino.write(action.encode())
                last = action
        socketio.sleep(1)    
        #arduino.close()


@app.route('/')
def index():
    return render_template('index.html', async_mode=socketio.async_mode)
  
@socketio.on('my_event', namespace='/test')
def test_message(message):   
    session['receive_count'] = session.get('receive_count', 0) + 1 
    session['A'] = message['value']    
    emit('my_response',
         {'data': message['value'], 'count': session['receive_count']})
 
@socketio.on('disconnect_request', namespace='/test')
def disconnect_request():
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my_response',
         {'data': 'Disconnected!', 'count': session['receive_count']})
    disconnect()

@socketio.on('connect', namespace='/test')
def test_connect():
    global thread
    with thread_lock:
        if thread is None:
            thread = socketio.start_background_task(target=background_thread, args=session._get_current_object())
    emit('my_response', {'data': 'Connected', 'count': 0})

@socketio.on('click_event', namespace='/test')
def db_message(message):
    session['btn_value'] = message['value'] 

@socketio.on('return_file_data', namespace='/test')
def db_message(message):
    socketio.emit('data_loaded', {'data':  read_from_file("output_data")}, namespace='/test')

@socketio.on('return_db_data', namespace='/test')
def db_message(message):
    socketio.emit('data_loaded', {'data':   read_from_db()}, namespace='/test')    
     

@socketio.on('disconnect', namespace='/test')
def test_disconnect():
    print('Client disconnected', request.sid)

if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=80, debug=True)    