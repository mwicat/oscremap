# -*- coding: utf-8 -*-

"""Console script for oscremap."""

import logging
import os
import sys

import click


from pythonosc import osc_server, udp_client
from pythonosc.dispatcher import Dispatcher

from .oscremap import (
    default_handler,
    remap_plugman,
)


DEVICE_MAPS_FN = os.path.join(
    os.path.expanduser('~'),
    'Documents/Isotonik/PrEditor/BCR_XL_device_map_24.xml'
)


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


@cli.command()
@click.pass_context
@click.argument('remote-ip')
@click.option('--ip',
              help='Local address for binding',
              default='127.0.0.1')
@click.option('--port',
              help='Local port for binding',
              default=9000)
@click.option('--remote-port',
              help='Remote port for connecting',
              default=9000)
@click.option('--mode',
              help='Remap mode to use')
def proxy(ctx, remote_ip, ip, port, remote_port, mode):
    client = udp_client.SimpleUDPClient(remote_ip, remote_port)

    dispatcher = Dispatcher()
    dispatcher.set_default_handler(default_handler)

    if mode == 'plugman':
        remap_plugman(client, dispatcher, DEVICE_MAPS_FN)

    server = osc_server.ThreadingOSCUDPServer(
        (ip, port), dispatcher)

    click.echo("Serving on: {}:{}".format(ip, port))
    click.echo("Sending to: {}:{}".format(remote_ip, remote_port))

    server.serve_forever()


def main():
    sys.exit(cli(obj={}))


if __name__ == '__main__':
    main()
