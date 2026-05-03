# Electrolux Home

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

This is an integration for connecting Electrolux devices which are controlled by the [Electrolux](https://apps.apple.com/pl/app/electrolux/id1595816832) app to Home Assistant.

## 🌡️ Supported devices

- Comfort 600 air conditioner
- Well A7 air purifier

## 🧰 Installation

### 🛒 HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to Integrations
3. Click the three dots menu and select "Custom repositories"
4. Add this repository: `https://github.com/tomekkleszcz/home-assistant-electrolux`
5. Select "Integration" as category
6. Click "Add"
7. Search for "Electrolux Home" and install it
8. Restart Home Assistant

### 🏗️ Manual Installation

1. Download the latest release
2. Copy `custom_components/electrolux` from this repository to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## 🧑‍💻 Development

This repository uses the standard HACS custom integration layout:

```text
custom_components/electrolux/
```

Start a local Home Assistant instance with the integration mounted into the dev config:

```bash
make dev
```

Home Assistant will be available at [http://localhost:8123](http://localhost:8123). The default image tag, port, and timezone are defined in `.env.example`; copy it to `.env` if you want local overrides.

Useful development commands:

```bash
make dev-up
make logs
make restart
make lint
make dev-down
make check
```

For runtime reloads of an existing config entry, create a long-lived access token in Home Assistant and run:

```bash
make reload-entry ENTRY_ID=<entry_id> HA_TOKEN=<token>
```

Home Assistant does not reliably re-import changed Python modules for custom integrations during config-entry reload. Use `make restart` after code changes. Use `make reload-entry` only for behavior that is handled by unloading and setting up the already loaded integration again.

## ⚙️ Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **Electrolux Home**
3. Enter your credentials:
   - **API Key**: Your Electrolux Developer API key
   - **Access Token**: OAuth2 access token
   - **Refresh Token**: OAuth2 refresh token
   - **Scan Interval**: How often to check for updates (default: 120 seconds)

### 🔐 Getting Your Credentials

1. Go to [Electrolux Developer Portal](https://developer.electrolux.one)
2. Create an account and register your application
3. Get your API Key from the dashboard
4. Generate Access Token and Refresh Token using OAuth2 flow

## ⚙️ Configuration Options

You can adjust the scan interval in the integration options:
- Go to **Settings** → **Devices & Services** → **Electrolux Home** → **Configure**
- Adjust the **Scan Interval** (in seconds)
