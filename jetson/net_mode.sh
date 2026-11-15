#!/bin/bash
# Switch the Jetson's Wi-Fi between the two modes (run as root):
#   sudo bash net_mode.sh demo      -> own Wi-Fi "InvoiceAgent": phones join it and open http://10.42.0.1:8400
#                                     (no internet, no Tailscale; the app accepts only these phones + USB cable)
#   sudo bash net_mode.sh online    -> back on the venue Wi-Fi (LAU_Guest + automatic login page) with Tailscale
#   sudo bash net_mode.sh status
#   sudo bash net_mode.sh demo --revert-after 120   -> safe test: goes back online by itself after 120 s
# The Wi-Fi chip (RTL8822CE) can't be a hotspot and a client at the same time, hence two modes.
set -u
APP=/home/elevai/alphahack
ENV="$APP/.env"
get() { grep -E "^$1=" "$ENV" 2>/dev/null | head -1 | cut -d= -f2-; }
SSID=$(get HOTSPOT_SSID); SSID=${SSID:-InvoiceAgent}
PASS=$(get HOTSPOT_PASS)
ONLINE_WIFI=$(get ONLINE_WIFI); ONLINE_WIFI=${ONLINE_WIFI:-LAU_Guest}
IF=wlP1p1s0
AP=InvoiceAgent-AP
LOG="$APP/data/net_mode.log"
mkdir -p "$APP/data"
log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

portal_login() {  # LAU guest portal (Cisco ISE): same steps as a browser login
  local user pass ua loc base p2 token portal
  user=$(get PORTAL_USER); pass=$(get PORTAL_PASS)
  [ -z "$user" ] && { log "no PORTAL_USER in .env: skip login page"; return; }
  ua="Mozilla/5.0 (X11; Linux aarch64) Chrome/120.0"
  for i in 1 2 3; do
    curl -s -m 10 -o /dev/null -w "%{http_code}" https://www.google.com/generate_204 | grep -q 204 && { log "internet OK"; return; }
    loc=$(curl -s -m 10 -D - -o /dev/null http://neverssl.com/ | grep -i "^location:" | head -1 | cut -d" " -f2- | tr -d "\r")
    [ -z "$loc" ] && { sleep 3; continue; }
    base=$(echo "$loc" | sed -n 's#\(https://[^/]*\)/.*#\1#p')
    p2=$(curl -s -m 20 -k -A "$ua" -c /tmp/portal.cookies -b /tmp/portal.cookies -L "$loc")
    token=$(echo "$p2" | grep -o 'name="token" value="[^"]*"' | head -1 | sed 's/.*value="\(.*\)"/\1/')
    portal=$(echo "$p2" | grep -o 'name="portal" value="[^"]*"' | head -1 | sed 's/.*value="\(.*\)"/\1/')
    p3=$(curl -s -m 25 -k -A "$ua" -c /tmp/portal.cookies -b /tmp/portal.cookies -L --data-urlencode "token=$token" \
      --data-urlencode "portal=$portal" --data-urlencode "user.username=$user" --data-urlencode "user.password=$pass" \
      --data-urlencode "aupAccepted=true" "$base/portal/LoginSubmit.action?from=LOGIN")
    token=$(echo "$p3" | grep -o 'name="token" value="[^"]*"' | head -1 | sed 's/.*value="\(.*\)"/\1/')
    curl -s -m 25 -k -A "$ua" -c /tmp/portal.cookies -b /tmp/portal.cookies -L --data-urlencode "token=$token" \
      "$base/portal/Continue.action?from=POST_ACCESS_BANNER" -o /dev/null
    sleep 6
  done
  curl -s -m 10 -o /dev/null -w "%{http_code}" https://www.google.com/generate_204 | grep -q 204 && log "internet OK" || log "internet NOT reachable"
}

ensure_ap() {
  [ -z "$PASS" ] && { log "HOTSPOT_PASS missing in .env"; exit 1; }
  if ! nmcli -t -f NAME con show | grep -qx "$AP"; then
    nmcli con add type wifi ifname "$IF" con-name "$AP" autoconnect no ssid "$SSID" \
      802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 \
      ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv6.method ignore \
      wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASS" >/dev/null && log "created hotspot profile $SSID"
  else
    nmcli con mod "$AP" 802-11-wireless.ssid "$SSID" wifi-sec.psk "$PASS"
  fi
}

case "${1:-status}" in
  demo)
    ensure_ap
    nmcli con mod "$AP" connection.autoconnect yes connection.autoconnect-priority 999   # stays in DEMO after reboot
    log "switching to DEMO: Wi-Fi $SSID, app http://10.42.0.1:8400"
    nmcli con up "$AP" >>"$LOG" 2>&1 && log "DEMO mode ON" || log "DEMO mode FAILED"
    if [ "${2:-}" = "--revert-after" ]; then
      sleep "${3:-120}"
      log "test finished: reverting to ONLINE"
      exec bash "$0" online
    fi
    ;;
  online)
    nmcli con mod "$AP" connection.autoconnect no 2>/dev/null
    nmcli con down "$AP" >/dev/null 2>&1
    log "switching to ONLINE: $ONLINE_WIFI"
    nmcli con up "$ONLINE_WIFI" >>"$LOG" 2>&1 || nmcli dev wifi connect "$ONLINE_WIFI" ifname "$IF" >>"$LOG" 2>&1
    sleep 4
    portal_login
    log "ONLINE mode ON ($(ip -4 -br a show $IF | awk '{print $3}'))"
    ;;
  status)
    nmcli -t -f NAME,DEVICE con show --active | grep "$IF" ;;
esac
