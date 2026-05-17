# boot.py
import network
import utime
import config
import gc

def do_connect():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('Conectando a la red...')
        wlan.connect(config.WIFI_SSID, config.WIFI_PASS)
        while not wlan.isconnected():
            utime.sleep(1)
            print(".", end="")
    print('\nConectado! IP:', wlan.ifconfig()[0])
    gc.collect()

do_connect()
