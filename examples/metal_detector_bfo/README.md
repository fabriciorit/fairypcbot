# Metal Detector BFO

A fully analog Beat-Frequency Oscillator (BFO) metal detector. 

This example showcases an analog circuit that uses two Colpitts oscillators mixed together. It features external off-board components (search coil L1 via J1, speaker SPK1 via J2, battery BAT1 via J3).

**Note**: The framework does not simulate circuits (no SPICE, by design). Tuning values are adjusted on the bench using trimmer CT1.

## Data Acquisition

This example requires fetching part data from LCSC using the `fae catalog fetch` command.
**Disclaimer**: The data obtained via `catalog fetch` is subject to the terms of its source (EasyEDA/LCSC). Verifying and complying with those terms is the user's responsibility.

Run the following commands to fetch the required components:

```bash
fae catalog fetch lcsc:C2942489
fae catalog fetch lcsc:C779738
fae catalog fetch lcsc:C22438596
fae catalog fetch lcsc:C2929436
fae catalog fetch lcsc:C295747
fae catalog fetch lcsc:C1525
fae catalog fetch lcsc:C5240379
fae catalog fetch lcsc:C48970601
fae catalog fetch lcsc:C51953428
fae catalog fetch lcsc:C19612851
fae catalog fetch lcsc:C25804
fae catalog fetch lcsc:C780220
fae catalog fetch lcsc:C9900021285
```

## Run

After fetching the required components, you can run the pipeline:

```bash
fae validate  -p examples/metal_detector_bfo
fae elaborate -p examples/metal_detector_bfo
fae place     -p examples/metal_detector_bfo
```
