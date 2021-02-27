# -*- coding: utf-8 -*-

"""Console script for oscremap."""

import logging
import os
import sys

import click
import mido
import rtmidi
import yaml

from pythonosc import udp_client

from .oscproxy import OSCProxy
from .qoscremap.qoscremap import get_app, get_window


logger = logging.getLogger(__name__)


@click.group()
@click.option('--debug/--no-debug', default=False)
@click.option('-l', '--loglevel', help='Logging level')
@click.pass_context
def cli(ctx, debug, loglevel):
    ctx.obj['DEBUG'] = debug
    if loglevel is not None:
        loglevel = getattr(logging, loglevel.upper(), None)
    else:
        loglevel = logging.INFO
    logging.basicConfig(level=loglevel)


def get_base_path():
    return os.path.expanduser('~/oscremap')


def get_config_path():
    return os.path.join(get_base_path(), 'config.yaml')


@cli.command()
@click.option('-c', '--config', default='default',
              help='Configuration name to generate')
def generate_config(config):
    """
    Generate configuration file.
    """
    config_path = get_config_path()

    midi_in = rtmidi.MidiIn()
    midi_out = rtmidi.MidiOut()

    config_template = {
        'global': {
            'params': 16,
            'params_in_row': 4,
        },
        'daw_osc': {
            'listen_ip': '127.0.0.1',
            'listen_port': 9001,
            'remote_ip': '127.0.0.1',
            'remote_port': 9002,
        },
        'controller_osc': {
            'listen_ip': '127.0.0.1',
            'listen_port': 9003,
            'remote_ip': '127.0.0.1',
            'remote_port': 9004,
        },
        'controller_midi': {
            'input_port': midi_in.get_ports(),
            'input_channel': 0,
            'output_port': midi_out.get_ports(),
            'output_channel': 0,
            'cc_param_start': 0,
            'cc_learn': 56
        },
    }

    if os.path.exists(config_path):
        cfg = yaml.safe_load(open(config_path))
    else:
        cfg = {}

    current_cfg = cfg.setdefault(config, {})

    for section in config_template:
        click.echo('Configuring section {}...'.format(section))
        section_defaults = config_template[section]
        section_cfg = {}
        current_cfg[section] = section_cfg

        for key, value in section_defaults.items():
            if isinstance(value, list):
                for idx, item in enumerate(value):
                    click.echo('{} - {}'.format(idx, item))
                choice = click.Choice([str(x) for x in range(len(value))])
                idx = click.prompt(
                    'Set value for "{}"'.format(key),
                    default='0',
                    type=choice)
                value = value[int(idx)]
            else:
                value = click.prompt(
                    'Set value for "{}"'.format(key),
                    default=value)
            section_cfg[key] = value

    click.echo('Result config "{}":'.format(config))
    click.echo(yaml.dump(current_cfg, indent=4))

    if click.confirm('Save configuration?'):
        open(config_path, 'w').write(yaml.dump(cfg))


@cli.command()
def ls_midi():
    """
    List available midi input and output ports
    """

    click.echo('Input ports:')
    for port in mido.get_input_names():
        click.echo('- {}'.format(port))

    click.echo('Output ports:')
    for port in mido.get_output_names():
        click.echo('- {}'.format(port))


@cli.command()
@click.option('-c', '--config', help='Configuration name to use',
              default='default')
@click.argument('addr')
@click.argument('args')
def send_osc(config, addr, args):
    """
    List available midi input and output ports
    """
    current_config = get_config(config)

    cfg_daw_osc = current_config['daw_osc']
    ctl_osc_client = udp_client.SimpleUDPClient(
        cfg_daw_osc['listen_ip'], cfg_daw_osc['listen_port'])
    ctl_osc_client.send_message(addr, eval(args))


def parse_config_file():
    config_path = get_config_path()
    logger.info('Reading configuration from {}'.format(config_path))
    if not os.path.exists(config_path):
        click.fail('Config file does not exist. Generate one with'
                   ' "oscremap generate-config"')
    cfg = yaml.safe_load(open(config_path))
    return cfg


@cli.command()
def ls_configs():
    """
    List available configs
    """
    cfg = parse_config_file()
    click.echo('Available configs:')
    for config in cfg:
        print(' - {}'.format(config))


@cli.command()
@click.argument('port')
def monitor_midi(port):
    """
    Monitor given midi input port for activity
    """

    port = mido.open_input(port)

    for msg in port:
        click.echo(msg)


def get_config(config_name):
    cfg = parse_config_file()
    current_config = cfg.get(config_name)

    while current_config is not None and 'alias' in current_config:
        config_name = current_config['alias']
        current_config = cfg.get(config_name)

    logger.info('Loaded config "{}"'.format(config_name))

    if current_config is None:
        click.fail(
            'Configuration "{}" does not exist.'
            ' Please run command "oscremap generate-config" first.'.format(
                config_name))

    current_config['fx_maps_path'] = os.path.join(
        get_base_path(), 'fxmaps', '{}.yaml'.format(config_name))

    return current_config


@cli.command()
@click.option('-c', '--config',
              multiple=True, default=["default"],
              help='Configuration name to use')
def proxy(config):
    """
    Start proxy between application and device.
    """

    app = get_app()
    windows = []
    osc_proxy_list = []

    for cfg in config:
        current_config = get_config(cfg)

        osc_proxy = OSCProxy(current_config)
        osc_proxy.start()
        osc_proxy_list.append(osc_proxy)

        window = get_window(
            current_config, osc_proxy.send_osc_to_internal_queue)
        windows.append(window)

    def on_close():
        pass  #message_server_thread.stop()

    app.lastWindowClosed.connect(on_close)

    sys.exit(app.exec_())


def main():
    sys.exit(cli(obj={}))


if __name__ == '__main__':
    main()
