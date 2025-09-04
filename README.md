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
2. Extract the `electrolux` folder to your `custom_components` directory
3. Restart Home Assistant

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
