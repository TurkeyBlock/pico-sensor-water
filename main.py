import network
import socket
import json
import time
import machine
import picozero

# Assign these variables with wi-fi credentials
SSID = ''
PASSWORD = ''

# Define water sensor
# These are the pins that have the data wire of each sensor attached
WATER_SENSOR_PIN = 1 #GP1

# Zabbix server details
ZABBIX_SERVER_IP = ''
ZABBIX_SERVER_PORT = 10051 #Listener port
HOST = 'pico-sensor'
WATER_KEY = 'water_key'


def connect_to_wlan():
    # Instantiate WLAN object, STA_IF sets as client to upstream wifi
    wlan = network.WLAN(network.STA_IF)
    
    # Set network interface to up
    wlan.active(True)
    
    # Connect to wifi with creds
    wlan.connect(SSID, PASSWORD)
    
    #Continued issues getting shunted to an unpected/unaccepted IP range.
    static_ip = ''  # Replace with your desired static IP
    subnet_mask = '255.255.255.0'
    gateway_ip = '' # Replace with your desired gateway IP
    dns_server = '8.8.8.8'

    wlan.ifconfig((static_ip, subnet_mask, gateway_ip, dns_server))
    # Retry connection until connected, flashes on-board LED
    while wlan.isconnected() == False:
        picozero.pico_led.toggle()
        print('Attempting WLAN login... LED will stop flashing when complete.')
        time.sleep(.5)
    
    # Grab ip address from WLAN object and return ip
    ip = wlan.ifconfig()[0]
    print(f'Connected on {ip}')
    return wlan

def check_wlan_and_reconnect(wlan):
    # Retry connection to wifi if disconnected
    while wlan.isconnected() == False:
        print('Lost connection. Reconnecting...')
        connect_to_wlan()
        
def water_sensor():
    # Read water sensor pin; returns 0 for no water and 1 for yes water
    water_data = machine.Pin(WATER_SENSOR_PIN, machine.Pin.IN)
    is_water = water_data.value()
    return is_water

def send_data_to_zabbix_server(zabbix_server_ip, zabbix_server_port, host, key, value):
    # Create socket object
    # AF_INET sets to IPv4 and SOCK_STREAM sets to TCP
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print('a')
    # Connect to Zabbix server
    s.connect((zabbix_server_ip, zabbix_server_port))
    print('b')
    # Prepare data in Zabbix sender protocol format
    data = {
        "request": "sender data",
        "data": [
            {
                "host": host,
                "key": key,
                "value": value
            }
        ]
    }

    # Serialize data as JSON
    data_json = json.dumps(data)
    print(data_json)

    # Prepare data to be sent as a binary packet
    zabbix_header = b'ZBXD\x01'
    data_len = len(data_json)
    data_to_send = zabbix_header + data_len.to_bytes(8, 'little') + data_json.encode()

    # Send data to Zabbix server
    s.sendall(data_to_send)

    # Receive response from Zabbix server
    response = s.recv(1024)
    print(response)

    # Close socket
    s.close()

    # Parse response and return result
    response_json = json.loads(response[13:])
    return response_json['info']
    

def main():
    # Connect to wifi, return wlan object to check if still connected in while loop
    wlan = connect_to_wlan()
    
    while True:
        # Try except block checks for wi-fi and sensor failures
        # No logging saved on pico-sensor, all data stored in memory and sent to Zabbix
        # Zabbix alerts can be modified to activate under certain conditions
        try:
            # Check for and retry wi-fi connection if connection is lost
            check_wlan_and_reconnect(wlan)
        except Exception as e:
            print(f'A WIFI error has occured: {e}')
            print('retrying... ')
        try:
            # Read water sensor
            is_water = water_sensor()
            
            # Added 2 x 1 second timers to not overload Pico
            # These split the sensor logic and each send_data_to_zabbix_server
            time.sleep(1)
            
            # Send water sensor value to  Zabbix server
            result = send_data_to_zabbix_server(ZABBIX_SERVER_IP, ZABBIX_SERVER_PORT, HOST, WATER_KEY, is_water)
            print(f'Water sensor value: {is_water}')
            print('Result:', result)
            time.sleep(1)
            
            #===
            #Planning to add here a wait-for-response from script hosted on the Zabbix server. (Remember to reopen Socket)
            #===
            
        except Exception as e:
            print(f'An error has occured: {e}')
            print('retrying... ')
            

if __name__ == '__main__':
    main()
