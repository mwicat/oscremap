import logging
from threading import Thread
import time

import xml.etree.ElementTree as ET


logger = logging.getLogger(__name__)


def default_handler(addr, *args):
    print('< %s: %s' % (addr, args))


def send_param(client, pnum, name=None, text=None, value=None):
    if name is not None:
        client.send_message("/plugman/param/%d/name" % pnum, name)
    if text is not None:
        client.send_message("/plugman/param/%d/text" % pnum, text)
    if value is not None:
        client.send_message("/plugman/param/%d/value" % pnum, value)


def remap_plugman(client, dispatcher, device_maps_fn):
    device_handler = DeviceHandler(client)

    def monitor_files():
        while True:
            with open(device_maps_fn) as device_maps_file:
                device_handler.device_maps = parse_device_maps(device_maps_file)
            logger.info('Refreshed maps from {}'.format(device_maps_fn))
            time.sleep(3)

    monitor_files_thread = Thread(target=monitor_files)
    monitor_files_thread.start()

    install_device_handler(dispatcher, device_handler)


class DeviceMap(object):

    def __init__(self, name, from_ui_map, to_ui_map):
        self.name = name
        self.from_ui_map = from_ui_map
        self.to_ui_map = to_ui_map

    def __repr__(self):
        return 'Device {} from_ui[{}] to_ui [{}]'.format(
            self.name, self.from_ui_map, self.to_ui_map)


def parse_device_maps(device_maps_file):
    data = device_maps_file.read()
    root = ET.fromstring(data)
    devices = root.findall(".//Device")
    device_maps = {}
    for device in devices:
        device_name = device.attrib['name']
        logger.debug('Found map for {}'.format(device_name))
        from_ui_map = {}
        to_ui_map = {}
        layout = device.find('./Layout')
        params = layout.attrib.copy()
        to_ui_map[0] = [0]
        for param_name, param_mapped in params.items():
            from_ui_param = int(param_name[1:]) + 1
            to_ui_param = int(param_mapped)
            from_ui_map[from_ui_param] = to_ui_param
            to_ui_map.setdefault(to_ui_param, []).append(from_ui_param)
        device_map = DeviceMap(device_name, from_ui_map, to_ui_map)
        device_maps[device_name] = device_map
    return device_maps


def clear_param(client, param_num):
    send_param(client, param_num, name=' ', text=' ', value=' ')


def install_device_handler(dispatcher, device_handler):
    dispatcher.map("/plugman/set_device", device_handler.handle_set_device)
    dispatcher.map("/plugman/set_params", device_handler.handle_set_params)
    dispatcher.map("/plugman/set_param", device_handler.handle_set_param)


class DeviceHandler(object):

    def __init__(self, client):
        self.client = client
        self.current_device = None
        self.device_maps = {}

    def handle_set_device(self, _addr, device):
        self.current_device = device

    def get_device_map(self):
        return self.device_maps.get(self.current_device)

    def to_ui_params(self, source_param):
        device_map = self.get_device_map()
        if device_map is not None:
            ui_params = device_map.to_ui_map.get(source_param)
        else:
            ui_params = [source_param]
        print('MAP source: {} ui: {}'.format(source_param, ui_params))
        return ui_params

    def handle_set_param(self, _addr, source_param, param_text, param_value):
        print('< set_param: %s' % [source_param, param_text, param_value])
        self.send_param(source_param, text=param_text, value=param_value)

    def send_param(self, source_param, name=None, text=None, value=None):
        ui_params = self.to_ui_params(source_param)
        print('ui_params', ui_params)
        if ui_params is not None:
            for ui_param in ui_params:
                send_param(
                    self.client, ui_param, name=name, text=text, value=value)
                print('send param {}->{} {} {} {}'.format(source_param, ui_param, name, text, value))
        return ui_params

    def handle_set_params(self, _addr, *params):
        print('< set_params: %s' % list(params))
        source_param = 0
        mapped_ui_params = set()
        for pnum in range(0, len(params), 3):
            param_name = params[pnum]
            param_text = params[pnum + 1]
            param_value = params[pnum + 2]
            ui_params = self.send_param(
                source_param, name=param_name, text=param_text, value=param_value)
            if ui_params:
                mapped_ui_params.update(ui_params)
            source_param += 1
        for ui_param in range(40):
            if ui_param not in mapped_ui_params:
                clear_param(self.client, ui_param)
