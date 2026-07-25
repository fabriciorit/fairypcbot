# LED Blinker 555

Minimal offline example — LED blinker with a 555 timer in astable mode.

This example uses only `class:` references from the founding library and requires no
network access or vendor data. It serves as a smoke test for the CI pipeline and as a
"hello world" for the framework.

## Run

```bash
fae validate  -p examples/led_blinker_555
fae elaborate -p examples/led_blinker_555
fae place     -p examples/led_blinker_555
```
