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
ZABBIX_SERVER_PORT = 10051 #Listener port for
ZABBIX_SCRIPT_PORT = 10052 #Listener port for requests
HOST = 'pico-sensor'       #Unique host name
WATER_KEY = 'water_key'
CRAC_KEY = 'crac_key'


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
    
def crac_switch():
    #Read switch pin; returns 0 for no override and 1 for disable CRAC unit.
    #Needs to be filled in.
    temp_switch_value = 0
    return temp_switch_value

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

#I *believe* a new socket connection is neccessary, as the Zabbix trap does not appear
# to be able to send information back after triggering the relevant script.
def request_data_from_zabbix_server(zabbix_server_ip, script_port, host, key):
    # Create socket object
    # AF_INET sets to IPv4 and SOCK_STREAM sets to TCP
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print('a')
    # Connect to server script
    s.connect((zabbix_server_ip, script_port))
    print('b')

    #Recieve connection confirmation
    requested_data = s.recv(1024)
    print(requested_data)
    
    #Send HOST (name of pi pico) & key
    data_to_send = bytes(host, 'utf-8') + b'\x00' + bytes(key, 'utf-8')
    s.sendall(data_to_send)
    
    #Recieve instructions
    requested_data = s.recv(1024)
    return_value = requested_data.decode()
    print(return_value)
    
    # Close socket
    s.close()

    return return_value

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

            #Read CRAC-unit switch
            is_on = crac_switch()
            
            # Added 2 x 1 second timers to not overload Pico
            # These split the sensor logic and each send_data_to_zabbix_server
            time.sleep(1)
            
            # Send water sensor value to  Zabbix server
            result = send_data_to_zabbix_server(ZABBIX_SERVER_IP, ZABBIX_SERVER_PORT, HOST, WATER_KEY, is_water)
            
            print(f'Water sensor value: {is_water}')
            print('Result:', result)
            time.sleep(1)

            #Send CRAC unit override status to Zabbix server
            #result = send_data_to_zabbix_server(ZABBIX_SERVER_IP, ZABBIX_SERVER_PORT, HOST, CRAC_KEY, is_on)

            #print(f'CRAC override value: {is_on}')
            #print('Result:', result)
        
        except Exception as e:
            print(f'An error has occured while reporting to Zabbix: {e}')
            print('retrying... ')
            
        tries = 0
        connected_to_script = False
        #Yes, tries could be set to 10 on success. No, don't do that.
        while(tries < 10 and connected_to_script == False):
            time.sleep(1)
            tries = tries + 1
            try:
                #Request CRAC instructions from the Zabbix script
                #Host is being used to check identity, Key is the relevant trapper in MySQL
                result = request_data_from_zabbix_server(ZABBIX_SERVER_IP, ZABBIX_SCRIPT_PORT, HOST, WATER_KEY)
                
                #Do whatever with the result. (Turn off CRAC unit)

                connected_to_script = True
            except Exception as e:
                print(f'An error has occured while requesting from Zabbix: {e}')
                print('retrying... ')
            
        #End of while, sleep (seconds) to save battery.
        time.sleep(10)

if __name__ == '__main__':
    main()
