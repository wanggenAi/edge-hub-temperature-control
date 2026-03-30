# Mosquitto MQTT Broker Deployment on Ubuntu

## 1. Purpose

This document records a minimum practical deployment path for a self-managed
MQTT broker on Ubuntu using Mosquitto.

The immediate goal is to provide a broker that can be used by:

- the ESP32 / Wokwi edge node
- the Python MQTT test client
- later parameter-downlink and ACK tests

The current deployment target is intentionally limited to a stable first step:

- public network access
- username / password authentication
- no forced TLS yet

TLS, ACL refinement, and further system hardening can be added later after the
basic broker path is fully verified.

## 2. Deployment Outcome

After completing this document, the server should provide:

- a running Mosquitto broker
- listener on port `1883`
- public network accessibility
- anonymous access disabled
- username / password authentication enabled
- local and remote publish / subscribe verification completed

## 3. Pre-Deployment Checks

### 3.1 Check Ubuntu version

Why:

- confirm the operating system baseline
- avoid path or service-name differences

Command:

```bash
lsb_release -a
```

Expected result:

- Ubuntu distribution information is displayed

If this fails, check:

- whether `lsb_release` is available
- otherwise use:

```bash
cat /etc/os-release
```

### 3.2 Check basic system status

Why:

- confirm the server has normal disk, memory, and time settings

Commands:

```bash
uname -a
df -h
free -h
timedatectl
```

Expected result:

- disk space is available
- memory usage is reasonable
- system time is normal

If this fails, check:

- disk usage
- network availability
- time synchronization

### 3.3 Check whether port 1883 is already in use

Why:

- avoid port conflicts before starting Mosquitto

Command:

```bash
sudo ss -ltnp | grep 1883
```

Expected result:

- no output if the port is free

If this fails, check:

- whether another MQTT broker or other service is already using port `1883`

## 4. Install Mosquitto and Client Tools

### 4.1 Update the package index

Why:

- make sure the latest available Ubuntu package metadata is used

Command:

```bash
sudo apt update
```

Expected result:

- package lists update successfully

If this fails, check:

- DNS resolution
- outbound network connectivity

### 4.2 Install Mosquitto and mosquitto-clients

Why:

- `mosquitto` provides the broker
- `mosquitto-clients` provides `mosquitto_pub` and `mosquitto_sub` for testing

Command:

```bash
sudo apt install -y mosquitto mosquitto-clients
```

Expected result:

- installation completes successfully

If this fails, check:

- whether `apt update` succeeded
- Ubuntu repository accessibility

## 5. Check Service Startup and Auto-Start

### 5.1 Check current service status

Why:

- confirm that the package-installed service exists and can run

Command:

```bash
sudo systemctl status mosquitto --no-pager
```

Expected result:

- `mosquitto.service` is present
- status is usually `active (running)` or at least recognized by systemd

If this fails, check:

- package installation success
- service name spelling

### 5.2 Enable auto-start

Why:

- ensure the broker starts automatically after a server reboot

Command:

```bash
sudo systemctl enable mosquitto
```

Expected result:

- a symlink creation message or confirmation from systemd

If this fails, check:

- whether `mosquitto.service` exists:

```bash
systemctl list-unit-files | grep mosquitto
```

## 6. Minimal Mosquitto Configuration

### 6.1 Confirm that the default config loads `conf.d`

Why:

- the cleanest Ubuntu-style method is to add a dedicated file under
  `/etc/mosquitto/conf.d/`

Command:

```bash
grep -n "include_dir" /etc/mosquitto/mosquitto.conf
```

Expected result:

- a line similar to:

```text
include_dir /etc/mosquitto/conf.d
```

If this fails, check:

- whether the package installed the default config correctly

### 6.2 Create a dedicated deployment config file

Recommended file:

- `/etc/mosquitto/conf.d/edge-control.conf`

Why:

- keeps custom MQTT configuration isolated
- makes rollback easier
- is consistent with Ubuntu package layout

Configuration content:

```conf
listener 1883
allow_anonymous false
password_file /etc/mosquitto/passwd
```

Create the file:

```bash
sudo tee /etc/mosquitto/conf.d/edge-control.conf > /dev/null <<'EOF'
listener 1883
allow_anonymous false
password_file /etc/mosquitto/passwd
EOF
```

Expected result:

- the file is created successfully

If this fails, check:

- `sudo` permission
- directory existence:

```bash
ls -ld /etc/mosquitto/conf.d
```

Why this configuration is chosen:

- `listener 1883`: standard MQTT TCP port
- `allow_anonymous false`: require authentication
- `password_file /etc/mosquitto/passwd`: simple and stable user management

At the current project stage, `password_file` is the preferred option because:

- it is easy to understand
- it is stable for a small broker
- it is sufficient for current ESP32 and Python testing

## 7. Create Username and Password

### 7.1 Create the password file and first user

Why:

- disabling anonymous access requires at least one valid user account

Command:

```bash
sudo mosquitto_passwd -c /etc/mosquitto/passwd edgeadmin
```

Expected result:

- the command prompts for a password twice
- after entering both, it returns without error

If this fails, check:

- write permission under `/etc/mosquitto/`
- whether the path exists

Important note:

- use `-c` only when creating the file for the first time
- using `-c` again later will overwrite the file

### 7.2 Set file ownership and permissions

Why:

- the password file contains credentials
- permissions should be restricted while remaining readable by Mosquitto

Commands:

```bash
sudo chown root:mosquitto /etc/mosquitto/passwd
sudo chmod 640 /etc/mosquitto/passwd
```

Expected result:

- no output if successful

If this fails, check:

- whether the `mosquitto` group exists:

```bash
getent group mosquitto
```

### 7.3 Add more users later if needed

Why:

- useful if separate credentials are needed for devices and test clients

Command:

```bash
sudo mosquitto_passwd /etc/mosquitto/passwd edgeclient
```

## 8. Restart and Validate the Broker

### 8.1 Perform a quick config check

Why:

- catch obvious configuration errors before relying on systemd restart results

Command:

```bash
mosquitto -c /etc/mosquitto/mosquitto.conf -v
```

Expected result:

- Mosquitto starts in the foreground
- configuration is accepted

After this quick check:

- press `Ctrl + C` to stop the foreground process

If this fails, check:

- config syntax
- password file existence
- password file permissions
- port conflicts

### 8.2 Restart the service

Why:

- apply the new configuration to the systemd-managed service

Command:

```bash
sudo systemctl restart mosquitto
```

Expected result:

- no output if the restart succeeds

If this fails, check:

- service status and logs in the next step

### 8.3 Check service status

Why:

- confirm the broker is actually running

Command:

```bash
sudo systemctl status mosquitto --no-pager
```

Expected result:

- status shows `active (running)`

If this fails, check:

- config syntax
- credentials file permissions
- whether another process is using port `1883`

### 8.4 Check service logs

Why:

- this is the most useful source of deployment error details

Commands:

```bash
sudo journalctl -u mosquitto -n 50 --no-pager
```

or for live logs:

```bash
sudo journalctl -u mosquitto -f
```

Expected result:

- normal startup logs
- later, client connection logs

If this fails, check:

- whether the service started at all
- whether the config path and password path are correct

## 9. Firewall Configuration

### 9.1 Check UFW status

Why:

- avoid changing firewall settings unnecessarily if UFW is disabled

Command:

```bash
sudo ufw status
```

Expected result:

- either `Status: inactive` or `Status: active`

### 9.2 If UFW is active, allow MQTT traffic

Why:

- permit remote TCP access to port `1883`

Commands:

```bash
sudo ufw allow 1883/tcp
sudo ufw reload
sudo ufw status
```

Expected result:

- `1883/tcp` appears as allowed

If this fails, check:

- whether UFW is actually being used
- whether a cloud firewall or security group also needs to be updated

Important note:

- if the server is on a cloud platform, the provider-side security group must
  also allow inbound `1883/tcp`

## 10. Local Self-Test on the Server

### 10.1 Start a local subscriber

Why:

- verify the broker works locally before testing remote access

Command:

```bash
mosquitto_sub -h 127.0.0.1 -p 1883 -u edgeadmin -P 'YOUR_PASSWORD' -t 'test/topic' -v
```

Expected result:

- the command waits for incoming messages

If this fails, check:

- username and password correctness
- whether the broker is running
- whether anonymous access is disabled and credentials were provided

### 10.2 Publish a local test message

Why:

- confirm that publish / subscribe works end to end

Command:

```bash
mosquitto_pub -h 127.0.0.1 -p 1883 -u edgeadmin -P 'YOUR_PASSWORD' -t 'test/topic' -m 'hello-mqtt'
```

Expected result:

- the subscriber terminal prints:

```text
test/topic hello-mqtt
```

If this fails, check:

- topic spelling
- username/password consistency
- whether the subscriber is still running

## 11. Remote Test from Another Machine

Assume the public IP or domain is:

- `YOUR_SERVER_IP_OR_DOMAIN`

### 11.1 Start a remote subscriber

Why:

- verify public network access and remote authentication

Command:

```bash
mosquitto_sub -h YOUR_SERVER_IP_OR_DOMAIN -p 1883 -u edgeadmin -P 'YOUR_PASSWORD' -t 'test/topic' -v
```

### 11.2 Publish a remote test message

Why:

- confirm that remote MQTT publish / subscribe works through the public broker

Command:

```bash
mosquitto_pub -h YOUR_SERVER_IP_OR_DOMAIN -p 1883 -u edgeadmin -P 'YOUR_PASSWORD' -t 'test/topic' -m 'remote-test'
```

Expected result:

- the remote subscriber receives:

```text
test/topic remote-test
```

If this fails, check in this order:

1. `sudo systemctl status mosquitto --no-pager`
2. `sudo journalctl -u mosquitto -n 50 --no-pager`
3. `sudo ufw status`
4. cloud firewall or security group rules
5. public IP or domain correctness
6. username / password correctness

## 12. Client Configuration Changes

Once the broker is running, the device-side and Python-side configuration
should be updated from the public test broker to the self-managed broker.

### 12.1 ESP32 / Wokwi side

Typical values to change:

- `host`
- `port`
- `username`
- `password`

Example:

```cpp
constexpr char kMqttHost[] = "YOUR_SERVER_IP_OR_DOMAIN";
constexpr uint16_t kMqttPort = 1883;
constexpr char kMqttUsername[] = "edgeadmin";
constexpr char kMqttPassword[] = "YOUR_PASSWORD";
```

When connecting, use a connect call that includes authentication.

### 12.2 Python client side

Example:

```python
BROKER_HOST = "YOUR_SERVER_IP_OR_DOMAIN"
BROKER_PORT = 1883
USERNAME = "edgeadmin"
PASSWORD = "YOUR_PASSWORD"
```

Before connecting:

```python
client.username_pw_set(USERNAME, PASSWORD)
client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
```

### 12.3 Current project topics

The current project topics can stay unchanged:

- `edge/temperature/edge-node-001/telemetry`
- `edge/temperature/edge-node-001/params/set`
- `edge/temperature/edge-node-001/params/ack`

## 13. Common Failure Points

### 13.1 Mosquitto service cannot start

Check:

```bash
sudo systemctl status mosquitto --no-pager
sudo journalctl -u mosquitto -n 100 --no-pager
```

Common causes:

- syntax error in the config file
- wrong `password_file` path
- wrong password-file permissions
- port conflict on `1883`

### 13.2 Local test works but remote access fails

Check:

```bash
sudo ufw status
sudo ss -ltnp | grep 1883
```

Common causes:

- UFW not allowing `1883/tcp`
- cloud security group not allowing `1883/tcp`
- no public IP or wrong domain

### 13.3 Client reports authorization error

Common causes:

- wrong username
- wrong password
- credentials omitted while `allow_anonymous false` is enabled

### 13.4 New user added but login still fails

First check:

```bash
sudo systemctl restart mosquitto
```

Then test again.

### 13.5 Broker appears to run but does not listen publicly

Check:

```bash
sudo ss -ltnp | grep mosquitto
```

Expected result:

- the listener should appear on `0.0.0.0:1883` or an externally reachable
  address

If it only listens on `127.0.0.1`, check:

- whether the config file was loaded
- whether another config overrides the listener

## 14. Minimal Rollback Plan

If the deployment config is broken, the smallest rollback method is to remove
the custom config from `conf.d` and restart the service.

### 14.1 Move the custom config out of the active directory

Command:

```bash
sudo mv /etc/mosquitto/conf.d/edge-control.conf /etc/mosquitto/conf.d/edge-control.conf.bak
```

### 14.2 Restart Mosquitto

Command:

```bash
sudo systemctl restart mosquitto
```

### 14.3 Re-check service state

Command:

```bash
sudo systemctl status mosquitto --no-pager
```

If needed, the password file can also be moved aside temporarily:

```bash
sudo mv /etc/mosquitto/passwd /etc/mosquitto/passwd.bak
```

This rollback approach keeps the package-installed default structure intact
while quickly removing the custom authentication configuration.

## 15. Next Step Preview

The next natural upgrade after this document is:

- add TLS on a dedicated listener such as `8883`
- update client connection settings for certificate-based secure transport
- later evaluate ACL and service hardening options
