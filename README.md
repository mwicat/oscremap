## Messages

### Receives messages to DAW

- `/fx/param/[PARAM_POS]/val` - FX parameter value at position `PARAM_POS`
- `/fx/param/[PARAM_POS]/name` - name of FX parameter at position `PARAM_POS`
- `/fx/param/[PARAM_POS]/str` - string representation of FX parameter value at position `PARAM_POS`
- `/fx/name [NAME]` - name of current FX
- `/fx/bypass [STATUS=1|0]` - bypass status of current FX
- `/fx/openui [STATUS=1|0]` - opened UI status of current FX

### Receives messages from DAW

- `/fx/param/[PARAM_POS]/val` - set FX parameter value at position `PARAM_POS`
- `/fx/select/prev` - select previous FX
- `/fx/select/next` - select next FX
- `/fx/bypass [STATUS=1|0]` - set bypass status of current FX
- `/fx/openui [STATUS=1|0]` - set opened UI status of current FX
