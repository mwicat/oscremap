# -*- coding: utf-8 -*-

"""Console script for qoscremap."""

import logging
import os
import sys

import click
import yaml

from .qoscremap import start_osc_ui


logger = logging.getLogger(__name__)


def get_config_path():
    return os.path.expanduser('~/oscremap/config.yaml')


def parse_config(ctx):
    config_path = get_config_path()
    logger.info('Reading configuration from {}'.format(config_path))
    if not os.path.exists(config_path):
        ctx.fail('Config file does not exist. Generate one with'
                   ' "oscremap generate-config"')
    cfg = yaml.safe_load(open(config_path))
    return cfg


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
@click.option('-c', '--config', default='default',
              help='Configuration name to use')
@click.pass_context
def start(ctx, config):
    """
    Start application.
    """
    cfg = parse_config(ctx)

    current_config = cfg.get(config)

    while current_config is not None and 'alias' in current_config:
        config = current_config['alias']
        current_config = cfg.get(config)

    logger.info('Loaded config {}'.format(config))

    if current_config is None:
        ctx.fail(
            'Configuration "{}" does not exist.'
            ' Please run command "oscremap generate-config" first.')

    start_osc_ui(current_config)


def main():
    sys.exit(cli(obj={}))


if __name__ == '__main__':
    main()
