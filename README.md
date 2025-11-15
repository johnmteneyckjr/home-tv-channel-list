# home-tv-channel-list

Generate a clean, laminated-ready, accordion-fold TV channel guide
for your home from a simple CSV file.

Features:

- 2-page PDF, landscape
- 4-column, column-major layout (great for quad-fold)
- Per-column header with your house name
- One line per channel (channel number + code)
- Color-coded by category (Local / News / Sports / Kids / Faith / Shop / Music / Intl / TV)
- Compact 2-line legend at the bottom of each column
- Dotted vertical fold guides for laminating & folding

## Files

- `channels.csv` — your channel list:
  - `number,code,description` (`description` is optional and shown only when enabled in config)
- `config.yaml` — house- and layout-level config
- `build_tv_channel_sheet.py` — main script

## Usage

```bash
pip install -r requirements.txt
python build_tv_channel_sheet.py
```

## Demo build script

To build the demonstration PDF that CI publishes to `./outputs/`:

```bash
./ci/build-demo.sh
```

## Optional channel logos

Logo fetching/rendering is powered by `fetch_channel_logos.py`, adapted from the kit in `../channel_logo_fetch_kit.zip`.  
Set `logos.enabled: true` in `config.yaml` to have `build_tv_channel_sheet.py` fetch and display square PNG logos (stored under `outputs/logos/`).  
Run the fetcher standalone if you only need the assets:

```bash
python fetch_channel_logos.py --channels-csv channels.csv --output-dir outputs/logos
```

If `logos.enabled` is `false`, the builder skips all logo work and sticks with the legacy text-only layout.

## Channel descriptions

`channels.csv` now supports an optional `description` column.  
Control whether that third column shows up via `channel_display.show_description` in `config.yaml`.  
When disabled (the default in the demo config), the sheet renders only channel numbers and call signs.

## Font tuning

All of the key font sizes live under the `fonts` block in `config.yaml`.  
To independently adjust the channel number vs. channel name sizing, tweak `fonts.cell_number_size` and `fonts.cell_name_size`.  
Other knobs like `fonts.header_size`, `fonts.legend_size`, and `fonts.cell_leading` let you dial in the final look for your printer/lamination workflow.
