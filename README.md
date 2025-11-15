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
  - `number,code`
- `config.yaml` — house- and layout-level config
- `build_tv_channel_sheet.py` — main script

## Usage

```bash
pip install -r requirements.txt
python build_tv_channel_sheet.py