# Clone and Setup Guide

This guide will help you quickly set up `rffl-boxscores` on any computer.

## Quick Setup (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/rffl-boxscores.git
cd rffl-boxscores

# 2. Run the setup script
./setup.sh

# 3. Activate the virtual environment
source venv/bin/activate

# 4. Set up your league configuration
echo 'export LEAGUE=YOUR_LEAGUE_ID' >> .env

# 5. Load vibe mode (optional)
source ./vibe.sh
```

## Manual Setup

If you prefer to set up manually:

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/rffl-boxscores.git
cd rffl-boxscores

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -e .

# 4. Test installation
python test_installation.py

# 5. Configure your league
echo 'export LEAGUE=YOUR_LEAGUE_ID' >> .env
```

## Configuration

### Public League
```bash
echo 'export LEAGUE=323196' >> .env
```

### Private League
```bash
echo 'export LEAGUE=YOUR_LEAGUE_ID' >> .env
echo 'export ESPN_S2="your_espn_s2_cookie_value"' >> .env
echo 'export SWID="{your_swid_cookie_value}"' >> .env
```

## Quick Test

```bash
# Test the CLI
rffl-bs --help

# Test with vibe mode
source ./vibe.sh
bs 2024
bsv 2024
bsl 2024
```

## Getting ESPN Cookies (Private Leagues)

1. Log into ESPN Fantasy Football in your browser
2. Open Developer Tools (F12)
3. Go to Application/Storage → Cookies → espn.com
4. Copy the values for:
   - `ESPN_S2` (long string)
   - `SWID` (format: `{...}`)

## Troubleshooting

### Python Version Issues
Make sure you have Python 3.9+ installed:
```bash
python3 --version
```

### Permission Issues
If setup.sh isn't executable:
```bash
chmod +x setup.sh
```

### Virtual Environment Issues
If you get import errors, make sure the virtual environment is activated:
```bash
source venv/bin/activate
```

### League Access Issues
- For public leagues: No authentication needed
- For private leagues: Make sure ESPN_S2 and SWID are set correctly
- Check that your league ID is correct

## File Structure

```
rffl-boxscores/
├── setup.sh              # Quick setup script
├── vibe.sh               # Quick aliases
├── .env                  # Your league configuration (create this)
├── rffl_boxscores/       # Main package
├── README.md             # Full documentation
└── CLONE_GUIDE.md        # This file
```

## Next Steps

After setup, you can:
1. Export fantasy football data: `rffl-bs export --league <id> --year 2024`
2. Validate data consistency: `rffl-bs validate <file>.csv`
3. Check lineup compliance: `rffl-bs validate-lineup <file>.csv`
4. Use vibe mode for quick commands: `source ./vibe.sh && bs 2024`

Happy fantasy football data analysis! 🏈
