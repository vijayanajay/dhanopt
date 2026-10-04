# Oracle Cloud Always Free VM Setup Guide (Baby Steps)

This guide walks you through setting up an **Always Free** cloud server on Oracle Cloud Infrastructure (OCI) to run the `dhanopt` 60-second option chain capture 24/7. It guarantees you never miss market data due to local power or internet outages.

---

## Overview

* **Cost:** ₹0 / month (Free forever on Oracle Always Free Tier)
* **Location:** Mumbai (`ap-mumbai-1`) or Hyderabad (`ap-hyderabad-1`)
* **Specs:** 1 OCPU, 1 GB RAM (AMD x86) or up to 4 OCPUs, 24 GB RAM (Ampere ARM)
* **Operating System:** Ubuntu 24.04 LTS Minimal
* **Run Schedule:** Mon–Fri 08:55 to 15:35 IST via Linux `cron`

---

## Step 1: Create an Oracle Cloud Account

1. Go to [oracle.com/cloud/free](https://www.oracle.com/cloud/free/).
2. Click **Start for free**.
3. Enter your country, name, and email address.
4. **Home Region selection (CRITICAL):**
   * Select **India West (Mumbai)** or **India South (Hyderabad)**.
   * *Note: You cannot change your Home Region later.* Mumbai gives <5ms network latency to NSE and Dhan servers.
5. Provide your address and phone number, then verify via SMS.
6. Enter a valid credit/debit card (Mastercard/Visa with international transactions enabled).
   * Oracle will make a temporary authorization charge (~₹80 to ₹100) which is immediately reversed.
   * **You will NOT be charged** as long as you stay within the Always Free tier.
7. Complete registration and log in to the Oracle Cloud Console.

---

## Step 2: Create the Free Compute Instance

1. In the OCI Console dashboard, click the navigation menu (top-left ☰) and select **Compute** → **Instances**.
2. Click **Create Instance**.
3. Configure the following fields:
   * **Name:** `dhanopt-collector`
   * **Create in compartment:** Leave as default (root compartment).
   * **Placement:** Leave default Availability Domain.
4. **Image and Shape:**
   * Click **Change Image**. Select **Canonical Ubuntu**, version **24.04** (or **22.04 Minimal**). Click **Select Image**.
   * Click **Change Shape**:
     * Option A (Recommended): Select **Ampere** (Arm-based Processor), `VM.Standard.A1.Flex`. Set **1 OCPU** and **6 GB Memory** (Always Free eligible).
     * Option B (Standard): Select **AMD**, `VM.Standard.E2.1.Micro` (1/8 OCPU, 1 GB RAM, Always Free eligible).
     * Click **Select Shape**.
5. **Networking:**
   * **Recommended (Easiest):**
     * If the *Public IPv4 address* toggle is greyed out (a known OCI UI bug when creating a subnet inline), you have two easy options:
       * **Option 1 (Cleanest):** In a separate browser tab, go to **Networking** → **Virtual Cloud Networks** → click **Start VCN Wizard** → choose **Create VCN with Internet Connectivity** → click **Next** and **Create**. Then back on this page, choose **Select existing virtual cloud network** and pick the public subnet.
       * **Option 2 (Fastest):** Proceed as-is with **Create new public subnet** and click **Create** at the bottom. Once the instance is created, go to **Attached VNICs** → click your VNIC → **IPv4 Addresses** → click the three dots `⋮` on your private IP → **Edit** → select **Ephemeral public IP** → **Update**.
   * If available directly: Ensure **Automatically assign public IPv4 address** is toggled ON.
6. **Save SSH Keys (CRITICAL):**
   * Select **Generate a key pair for me**.
   * Click **Save private key** and save `ssh-key.key` to your local PC (e.g. `C:\Users\YourUser\.ssh\oci_dhanopt.key`).
   * *Do not skip this—you cannot connect without this key.*
7. **Boot Volume:**
   * Leave default (47 GB, well within the 200 GB free limit).
8. Click **Create** (bottom of the page).
   * Wait 1–2 minutes until the instance state changes from *Provisioning* (yellow) to **Running** (green).
   * Note down the **Public IP Address** (e.g. `140.238.xxx.xxx`).

---

## Step 3: Connect via SSH from Windows

1. Open **PowerShell** or **Command Prompt** on your Windows PC.
2. If your saved key file is at `C:\Users\user\.ssh\oci_dhanopt.key`, restrict its permissions (Windows requirement for SSH):
   ```powershell
   icacls "oci_dhanopt.key" /inheritance:r
   icacls "oci_dhanopt.key" /grant:r "$($env:USERNAME):(R)"
   ```
3. Connect to the instance using the `ubuntu` username:
   ```powershell
   ssh -i "oci_dhanopt.key" ubuntu@<YOUR_PUBLIC_IP>
   ```
   *(Type `yes` when prompted to accept host fingerprint).*

You are now in your cloud Ubuntu terminal!

---

## Step 4: Initial Server Configuration (5 Minutes)

Run these commands inside your cloud terminal:

### 4.1 Set Timezone to Indian Standard Time (IST)
The market runs on IST. Setting system time to IST prevents cron scheduling mistakes:
```bash
sudo timedatectl set-timezone Asia/Kolkata
date
# Output should show: Sun Oct 04 10:00:00 IST 2026
```

### 4.2 Update Packages & Install Tools
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git curl htop
```

---

## Step 5: Install and Configure `dhanopt`

### 5.1 Clone Your Repository
```bash
cd ~
git clone https://github.com/<your-username>/dhanopt.git
cd dhanopt
```

### 5.2 Set Up Python Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt requests
```

### 5.3 Configure Secrets (.env)
Create your `.env` configuration file on the server:
```bash
nano .env
```
Paste your Dhan API credentials:
```env
DHAN_CLIENT_ID="your_client_id_here"
DHAN_ACCESS_TOKEN="your_dhan_access_token_here"
```
Press `Ctrl + O`, then `Enter` to save, and `Ctrl + X` to exit `nano`.

### 5.4 Test the Capture Script (Smoke Test)
Run a test snapshot with `--force` (even on weekends/holidays):
```bash
python3 -m experiments.e009_wall_capture.capture_chains --force
```
You should see:
```json
{
 "date": "2026-10-04",
 "n_snapshots": 1,
 ...
}
```
If you see this, your credentials, network access, and parser are working properly!

---

## Step 6: Automate with Linux Cron (Set and Forget)

The repo includes a watchdog supervisor ([`watchdog.py`](experiments/e009_wall_capture/watchdog.py)) that automatically launches `capture_chains.py`, recovers from network blips, and exits cleanly at 15:35 IST.

1. Open crontab:
   ```bash
   crontab -e
   ```
   *(Select `1` for nano if prompted).*

2. Add the following lines to the bottom of the file:
   ```cron
   # Mon-Fri at 08:55 AM IST: Launch Dhan Option Chain Capture Watchdog
   55 08 * * 1-5 cd /home/ubuntu/dhanopt && /home/ubuntu/dhanopt/.venv/bin/python3 -m experiments.e009_wall_capture.watchdog >> /home/ubuntu/dhanopt/capture.log 2>&1
   ```

3. Save and exit (`Ctrl + O`, `Enter`, `Ctrl + X`).

4. Verify your crontab:
   ```bash
   crontab -l
   ```

The cloud VM is now fully armed. At 08:55 AM IST every Monday through Friday, it will wake up, capture every 60 seconds of full-depth dual-expiry option chains until 15:35 IST, write to compressed gzip files, and record coverage in `coverage_ledger.json`.

---

## Step 7: How to Download Daily Data to Your Local Windows PC

All snapshots are saved locally on the VM at:
`/home/ubuntu/dhanopt/experiments/e009_wall_capture/snapshots/YYYY-MM-DD.jsonl.gz`

### Method A: One-Command Download via SCP (Simplest)
Whenever your local PC is turned on, run this in Windows PowerShell:
```powershell
# Pull all snapshots from cloud VM to local PC
scp -i "C:\Users\user\.ssh\oci_dhanopt.key" -r ubuntu@<YOUR_PUBLIC_IP>:/home/ubuntu/dhanopt/experiments/e009_wall_capture/snapshots/ d:\Code\dhanopt\experiments\e009_wall_capture\snapshots\

# Pull updated coverage ledger
scp -i "C:\Users\user\.ssh\oci_dhanopt.key" ubuntu@<YOUR_PUBLIC_IP>:/home/ubuntu/dhanopt/experiments/e009_wall_capture/artifacts/coverage_ledger.json d:\Code\dhanopt\experiments\e009_wall_capture\artifacts\coverage_ledger.json
```

### Method B: Automated Cloudflare R2 / AWS S3 Sync
If you prefer the cloud VM to push the day's file to an S3 or Cloudflare R2 bucket right at 15:36 IST:
1. Install `rclone` on the VM:
   ```bash
   sudo apt install -y rclone
   rclone config  # Configure your R2/S3 remote e.g. 'myr2'
   ```
2. In your crontab on the VM, add a post-market sync at 15:40 IST:
   ```cron
   40 15 * * 1-5 rclone copy /home/ubuntu/dhanopt/experiments/e009_wall_capture/snapshots/ myr2:dhanopt-backup/snapshots/ >> /home/ubuntu/dhanopt/sync.log 2>&1
   ```
3. On your local PC, run:
   ```powershell
   rclone copy myr2:dhanopt-backup/snapshots/ d:\Code\dhanopt\experiments\e009_wall_capture\snapshots\
   ```

---

## Step 8: Important Oracle Cloud Gotchas & Maintenance

1. **Token Refreshing:**
   * Dhan API access tokens expire periodically (typically 24 hours to 30 days depending on your Dhan developer plan).
   * Update `DHAN_ACCESS_TOKEN` in `/home/ubuntu/dhanopt/.env` whenever you generate a new token. You do not need to restart anything—the next day's cron job will automatically pick up the new token.

2. **Preventing Oracle "Idle Instance" Reclaim:**
   * Oracle Cloud's Always Free policy reclaims compute instances if CPU utilization is under 20% for 7 consecutive days.
   * **Solution 1:** In your OCI Console, upgrade your account to **"Pay As You Go"**. Entering your card details permanent-exempts your account from idle VM reclamation while remaining 100% free if you stay within free tier limits.
   * **Solution 2:** Add a small periodic maintenance task in cron:
     ```cron
     # Small 1-minute CPU wake-up every 6 hours to prevent idle flags
     0 */6 * * * dd if=/dev/urandom of=/dev/null bs=1M count=2000 status=none
     ```

3. **Checking Status Any Time:**
   SSH into the VM and check the log:
   ```bash
   tail -f /home/ubuntu/dhanopt/capture.log
   ```
