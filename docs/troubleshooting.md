# Troubleshooting

## DAW does not react to parameter changes from oscremap

Check if control surface script in DAW had successfully bound receiving port.

### Example

Logs:

```
INFO:oscremap.oscproxy:Initializing controller osc client to 127.0.0.1:9007
INFO:oscremap.oscproxy:Initializing daw osc client to 127.0.0.1:9004
INFO:oscremap.oscproxy:Initializing midi input port "Midi Fighter Twister" param channel 0 cmd channel 3 output port "Midi Fighter Twister"
INFO:oscremap.oscproxy:Available input ports: ['IAC Driver Bus 1', 'IAC Driver Bus 2', 'Midi Fighter Twister', 'Scarlett 18i20 USB', 'Bome MIDI Translator 1', 'Kimidi Input']
INFO:oscremap.oscproxy:Available output ports: ['IAC Driver Bus 1', 'IAC Driver Bus 2', 'Midi Fighter Twister', 'Scarlett 18i20 USB', 'Bome MIDI Translator 1', 'Kimidi Output']
INFO:oscremap.oscproxy:Initializing daw osc server on 127.0.0.1:9005
INFO:oscremap.oscproxy:Initializing controller osc server on 127.0.0.1:9006
```

That means DAW control surface script should have already bound port 9004 on its side.

Verification (MacOS):

```
$ lsof -i :9004
COMMAND   PID   USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
Live    99917    (...)  UDP localhost:9004
```
