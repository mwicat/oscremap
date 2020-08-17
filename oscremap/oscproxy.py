import logging
import time
import threading
import os
from queue import Queue, Empty

import rtmidi
from rtmidi.midiconstants import CONTROL_CHANGE
import yaml

from bidict import bidict

from pythonosc import osc_server, udp_client
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_message_builder import OscMessageBuilder
from pythonosc.osc_bundle_builder import OscBundleBuilder, IMMEDIATELY


logger = logging.getLogger(__name__)


FX_MAPS_PATH = os.path.expanduser('~/.oscremap_fxmaps.yaml')


class OSCProxy(object):

    def __init__(self, cfg):
        self.fx_name = ''
        self.learn_active = False
        self.fx_follow = True

        self.cfg_global = cfg_global = cfg['global']
        self.cfg_ctl_midi = cfg_ctl_midi = cfg['controller_midi']
        self.cfg_ctl_osc = cfg_ctl_osc = cfg['controller_osc']
        self.cfg_daw_osc = cfg_daw_osc = cfg['daw_osc']

        midi_cc_param_map = {
            (cfg_ctl_midi['cc_param_start'] + i): (i + 1)
            for i in range(cfg_global['params'])
        }

        self.num_params = cfg_global['params']

        self.cc_param_start = self.cfg_ctl_midi['cc_param_start']
        self.cc_param_end = self.cc_param_start + self.num_params

        self.midi_cc_param_map = bidict(midi_cc_param_map)

        self.fx_maps = self.load_fx_maps()

        self.source_target_map = bidict()

        self.learn_active = False
        self.learn_source = None
        self.learn_target = None
        self.bypass_fx = False

        logger.info('Initializing controller osc client to {}:{}'.format(
            cfg_ctl_osc['remote_ip'], cfg_ctl_osc['remote_port']
        ))

        self.ctl_osc_client = udp_client.SimpleUDPClient(
            cfg_ctl_osc['remote_ip'], cfg_ctl_osc['remote_port'])

        logger.info('Initializing daw osc client to {}:{}'.format(
            cfg_daw_osc['remote_ip'], cfg_daw_osc['remote_port']
        ))

        self.to_app_client = udp_client.SimpleUDPClient(
            cfg_daw_osc['remote_ip'], cfg_daw_osc['remote_port'])

        self.midi_in = rtmidi.MidiIn()
        self.midi_out = rtmidi.MidiOut()

        in_ports = self.midi_in.get_ports()
        out_ports = self.midi_out.get_ports()

        logger.info(
            'Initializing midi'
            ' input port "{}" param channel {}'
            ' cmd channel {} output port "{}"'.format(
            cfg_ctl_midi['input_port'],
            cfg_ctl_midi['param_channel'],
            cfg_ctl_midi['cmd_channel'],
            cfg_ctl_midi['output_port']
        ))

        self.midi_in_port = in_ports.index(cfg_ctl_midi['input_port'])
        self.midi_channel_param = cfg_ctl_midi['param_channel']
        self.midi_channel_cmd = cfg_ctl_midi['cmd_channel']

        self.midi_out_port = out_ports.index(cfg_ctl_midi['output_port'])

        self.midi_in.set_callback(self.handle_midi_from_ctl)

        self.daw_osc_dispatcher = Dispatcher()
        self.daw_osc_dispatcher.map('/*', self.handle_osc_from_daw)

        self.ctl_osc_dispatcher = Dispatcher()
        self.ctl_osc_dispatcher.map('/*', self.handle_osc_from_ctl)

        logger.info('Initializing daw osc server on {}:{}'.format(
            cfg_daw_osc['listen_ip'], cfg_daw_osc['listen_port']
        ))

        self.daw_osc_server = osc_server.BlockingOSCUDPServer(
            (cfg_daw_osc['listen_ip'], cfg_daw_osc['listen_port']),
            self.daw_osc_dispatcher)
        self.daw_osc_thread = threading.Thread(
            target=self.daw_osc_server.serve_forever)

        logger.info('Initializing controller osc server on {}:{}'.format(
            cfg_ctl_osc['listen_ip'], cfg_ctl_osc['listen_port']
        ))

        self.ctl_osc_server = osc_server.BlockingOSCUDPServer(
            (cfg_ctl_osc['listen_ip'], cfg_ctl_osc['listen_port']),
            self.ctl_osc_dispatcher)

        self.ctl_osc_thread = threading.Thread(
            target=self.ctl_osc_server.serve_forever)

        self.send_osc_to_ctl_queue = Queue()
        self.send_osc_to_ctl_thread = threading.Thread(
            target=self.consume_ctl_osc_queue)
        self.send_interval = 0.01

        self.send_midi_to_ctl_queue = Queue()
        self.send_midi_to_ctl_thread = threading.Thread(
            target=self.consume_send_midi_to_ctl_queue)

    def load_fx_maps(self):
        if not os.path.exists(FX_MAPS_PATH):
            return {}

        with open(FX_MAPS_PATH) as f:
            data = yaml.safe_load(f)
            return {
                fx_name: bidict(fx_map) for fx_name, fx_map in data.items()
            }

    def save_fx_maps(self):
        with open(FX_MAPS_PATH, 'w') as f:
            data = {
                fx_name: dict(fx_map) for fx_name, fx_map in self.fx_maps.items()
            }
            yaml.dump(data, f)

    def refresh_fx(self):
        self.to_app_client.send_message("/fx/select/prev", 1)
        self.to_app_client.send_message("/fx/select/next", 1)

    def clear(self):
        self.source_target_map.clear()
        self.save_fx_maps()
        self.init_osc_device_params()
        self.init_midi_device_params()
        self.refresh_fx()

    def consume_ctl_osc_queue(self):
        bundle_builder = OscBundleBuilder(IMMEDIATELY)
        last_send_time = 0
        while True:
            try:
                item = self.send_osc_to_ctl_queue.get_nowait()
            except Empty:
                time.sleep(0.005)
            else:
                address, values = item
                msg_builder = OscMessageBuilder(address=address)
                for value in values:
                    msg_builder.add_arg(value)
                msg = msg_builder.build()
                bundle_builder.add_content(msg)

            if not bundle_builder._contents:
                continue

            curr_time = time.time()
            if curr_time - last_send_time > self.send_interval:
                bundle = bundle_builder.build()
                self.ctl_osc_client.send(bundle)
                bundle_builder = OscBundleBuilder(IMMEDIATELY)
                last_send_time = curr_time

    def consume_send_midi_to_ctl_queue(self):
        while True:
            msg = self.send_midi_to_ctl_queue.get()
            print('midi send', msg)
            self.midi_out.send_message(msg)

    def init_osc_device_params(self):
        for param_num in range(1, 17):
            self.send_osc_to_ctl(
                f"/fx/param/{param_num}/str", '')
            self.send_osc_to_ctl(
                f"/fx/param/{param_num}/name", '')
            self.send_osc_to_ctl(
                f"/fx/param/{param_num}/val", 0)

    def init_osc_device(self):
        self.send_osc_to_ctl(
            f"/fx/learn", 0)
        self.send_osc_to_ctl(
            "/fx/name", '')
        self.init_osc_device_params()

    def init_midi_device_params(self):
        for cc in self.midi_cc_param_map.keys():
            self.send_midi_to_ctl(cc, 0)

    def init_midi_device(self):
        self.init_midi_device_params()

    def handle_osc_from_daw(self, addr, *args):
        #print('OSC RECV: %s %s' % (addr, args))
        if 'bypass' in addr:
            print('bypassss', addr)

        if addr == '/fx/name':
            fx_name = args[0]
            logger.info('Set FX: %s', fx_name)
            self.set_fx(fx_name)
            self.send_osc_to_ctl(
                "/fx/name", fx_name)
            self.init_osc_device_params()
            self.init_midi_device_params()

        elif addr.startswith('/fx/param/'):
            fields = addr.split('/')
            target_param = int(fields[-2])
            param_attr = fields[-1]

            if param_attr == 'val' and self.learn_active:
                self.set_learn_target(target_param)

            try:
                source_param = self.source_target_map.inverse[target_param]
            except KeyError:
                return

            prefix = f"/fx/param/{source_param}"

            if param_attr == 'name':
                name = args[0]
                self.send_osc_to_ctl(
                    f"{prefix}/name", name)
            if param_attr == 'val':
                val = float(args[0])
                self.send_osc_to_ctl(
                    f"{prefix}/val", val)
                cc = self.midi_cc_param_map.inverse[source_param]
                midi_val = int(val * 127)
                self.send_midi_to_ctl(cc, midi_val)
            elif param_attr == 'str':
                s = args[0]
                self.send_osc_to_ctl(
                    f"{prefix}/str", s)
        elif addr == '/fx/bypass':
            print('bypass', args)

    def handle_osc_from_ctl(self, addr, *args):
        if addr.startswith('/fx/param/'):
            fields = addr.split('/')
            source_param = int(fields[-2])

            param_attr = fields[-1]

            if param_attr == 'val' and self.learn_active:
                self.set_learn_source(source_param)

            try:
                target_param = self.source_target_map[source_param]
            except KeyError:
                return

            prefix = f"/fx/param/{target_param}"
            if param_attr == 'val':
                self.to_app_client.send_message(
                    f"{prefix}/val", args[0])
        elif addr == '/fx/learn':
            self.toggle_learn()
        elif addr == '/fx/clear':
            self.clear()

    def toggle_fx_follow(self):
        self.fx_follow = not self.fx_follow
        if self.fx_follow:
            print('follow focused')
            self.to_app_client.send_message(
                "/device/fx/follows/focused", 1)
        else:
            print('follow device')
            self.to_app_client.send_message(
                "/device/fx/follows/device", 1)

    def handle_midi_from_ctl(self, event, data=None):
        msg, deltatime = event
        logger.info('MIDI RECV: %s', msg)

        if msg[0] == (CONTROL_CHANGE | self.midi_channel_cmd):
            cc, value = msg[1], msg[2]
            if cc == self.cfg_ctl_midi['cc_toggle_ui'] and value == 127:
                self.send_osc_to_ctl('/toggle_ui', 1)
            elif cc == self.cfg_ctl_midi['cc_bypass_fx'] and value == 127:
                self.bypass_fx = not self.bypass_fx
                self.to_app_client.send_message("/fx/bypass", int(self.bypass_fx))
            elif cc == self.cfg_ctl_midi['cc_prev_fx'] and value == 127:
                self.to_app_client.send_message("/fx/select/prev", 1)
            elif cc == self.cfg_ctl_midi['cc_fx_follow'] and value == 127:
                self.toggle_fx_follow()
            elif cc == self.cfg_ctl_midi['cc_next_fx'] and value == 127:
                self.to_app_client.send_message("/fx/select/next", 1)
            elif cc == self.cfg_ctl_midi['cc_learn'] and value == 127:
                self.toggle_learn()

        if msg[0] == (CONTROL_CHANGE | self.midi_channel_param):
            cc, value = msg[1], msg[2]

            if self.cc_param_start <= cc <= self.cc_param_end:
                source_param = self.midi_cc_param_map[cc]

                if self.learn_active:
                    self.set_learn_source(source_param)
                    return

                try:
                    target_param = self.source_target_map[source_param]
                except KeyError:
                    return

                prefix = f"/fx/param/{target_param}"

                osc_val = value / 127.0
                self.to_app_client.send_message(
                    f"{prefix}/val", osc_val)

    def set_fx(self, fx_name):
        self.fx_name = fx_name
        try:
            source_target_map = self.fx_maps[fx_name]
        except KeyError:
            source_target_map = bidict()
            self.fx_maps[fx_name] = source_target_map
        self.source_target_map = source_target_map

    def set_learn_target(self, param_num):
        if self.learn_source is None:
            return
        self.learn_target = param_num
        logger.info('Learn target set to: %d', param_num)
        self.learn_check()

    def set_learn_source(self, param_num):
        self.learn_source = param_num
        logger.info('Learn source set to: %d', param_num)
        self.learn_check()

    def learn_check(self):
        if self.learn_source is None or self.learn_target is None:
            return
        logger.info(
            'Learned source: %s, target: %s',
            self.learn_source,
            self.learn_target)
        self.source_target_map.forceput(self.learn_source, self.learn_target)
        self.learn_source = None
        self.learn_target = None
        self.save_fx_maps()
        self.init_osc_device_params()
        self.init_midi_device_params()
        self.refresh_fx()

    def send_midi_to_ctl(self, cc, val, channel=None):
        if channel is None:
            channel = self.midi_channel_param
        self.send_midi_to_ctl_queue.put(
            [CONTROL_CHANGE | channel, cc, val])

    def send_osc_to_ctl(self, address, *args):
        logger.debug('Sending to controller: %s %s', address, args)
        self.send_osc_to_ctl_queue.put((address, args))

    def start(self):
        self.daw_osc_thread.start()
        self.ctl_osc_thread.start()
        self.send_osc_to_ctl_thread.start()
        self.send_midi_to_ctl_thread.start()

        self.midi_in.open_port(self.midi_in_port)
        self.midi_out.open_port(self.midi_out_port)

        self.init_osc_device()
        self.init_midi_device()

        self.refresh_fx()

    def toggle_learn(self):
        self.learn_active = not self.learn_active

        if self.learn_active:
            logger.info('Learn activated')
        else:
            logger.info('Learn disactivated')

        self.learn_source = None
        self.learn_target = None

        self.send_osc_to_ctl(
            f"/fx/learn", 1 if self.learn_active else 0)
        self.refresh_fx()
