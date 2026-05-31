# Three Terminal Applications - Complete Guide

## Overview

Three Python applications that communicate across separate terminal instances using a **shared JSON file** as the exchange mechanism.

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  TERMINAL 1                TERMINAL 3               TERMINAL 2
│  (Generator)              (Supervisor)             (Processor)
│                                                             │
│  • Asks user for           • Monitors T1           • Waits for
│    a number               • Verifies sum             decimals
│  • Calculates sum           is correct            • Calculates
│    from 1 to N            • Asks user for          decimal sum
│  • Writes to                approval              • Reports
│    shared file            • Generates              completion
│                             decimal numbers
│                           • Sends to T2
│
│  ↓ WRITES              ↓ READS/WRITES           ↓ READS/WRITES
│
│         ┌──────────────────────────────────────────┐
│         │    shared_state.json (on disk)           │
│         │                                          │
│         │  {                                       │
│         │    "number": 5,                          │
│         │    "sum_integer": 15,                    │
│         │    "app3_approved": true,                │
│         │    "decimal_numbers": [0.1, 0.2, ...],  │
│         │    "sum_decimal": 1.5,                   │
│         │    "finished": true                      │
│         │  }                                       │
│         └──────────────────────────────────────────┘
│
└─────────────────────────────────────────────────────────────┘

Data Flow:
  T1 writes → shared file → T3 reads → T3 writes → T2 reads
```

---

## Application Details

### Application 1: Generator (`app1_generator.py`)
**Runs in Terminal 1**

**What it does:**
1. Asks user to input a number
2. Calculates sum from 1 to that number (formula: n*(n+1)/2)
3. Writes the number and sum to `shared_state.json`
4. Waits for Terminal 3 to approve the calculation
5. Once approved, returns to waiting for new input

**Example:**
```
Enter a number: 5
✓ Calculated sum from 1 to 5
📊 Sum = 15
📝 Written to shared file
⏳ Waiting for Terminal 3 to approve...
✅ Terminal 3 APPROVED the number!
```

---

### Application 2: Processor (`app2_processor.py`)
**Runs in Terminal 2**

**What it does:**
1. Monitors the shared file for decimal numbers from Terminal 3
2. When decimals arrive, calculates their sum
3. Updates the shared file with the result
4. Notifies Terminal 3 that task is complete

**Example:**
```
⏳ Waiting for Terminal 3 to provide decimal numbers...
✅ Received 5 decimal numbers from Terminal 3
📥 Received: [0.1, 0.2, 0.3, 0.4, 0.5]
🔢 Calculating sum of decimal numbers...
   Sum = 1.5
✓ Updated shared file
📤 Notified Terminal 3 that task is finished
```

---

### Application 3: Supervisor (`app3_supervisor.py`)
**Runs in Terminal 3**

**What it does:**
1. Monitors Terminal 1 for the calculated sum
2. Verifies if the sum is mathematically correct
3. Asks user to approve/reject the sum
4. If approved, generates decimal numbers (0.1, 0.2, ... n*0.1)
5. Sends decimals to Terminal 2 for processing
6. Monitors Terminal 2 for completion

**Example:**
```
✅ Terminal 1 generated a sum
VERIFICATION RESULT
📊 Number provided: 5
📊 Sum calculated: 15
✓ Expected sum: 15
✅ Sum is CORRECT!
❓ Do you approve this sum? (yes/no): yes
✅ You approved the sum!
📋 Generating 5 decimal numbers...
   Generated: [0.1, 0.2, 0.3, 0.4, 0.5]
✓ Sent to Terminal 2
⏳ Waiting for Terminal 2 to process...
✅ Terminal 2 COMPLETED!
   Decimal Sum: 1.5
```

---

## How to Run

### Step 1: Open Three Terminal Windows

Open three separate terminal windows/tabs:
- Terminal Window 1 (for app1_generator.py)
- Terminal Window 2 (for app2_processor.py)
- Terminal Window 3 (for app3_supervisor.py)

### Step 2: Navigate to Application Directory

In each terminal, navigate to the directory containing the three Python files:

```bash
cd /path/to/applications
```

### Step 3: Start Application 2 and 3 First (Waiting Mode)

In **Terminal 2**, run:
```bash
python3 app2_processor.py
```

In **Terminal 3**, run:
```bash
python3 app3_supervisor.py
```

Both will show "Waiting..." messages since Terminal 1 hasn't provided input yet.

### Step 4: Start Application 1

In **Terminal 1**, run:
```bash
python3 app1_generator.py
```

### Step 5: Interact

**In Terminal 1:**
- You'll be prompted to enter a number
- Type a number (e.g., `5`)
- The app calculates sum and writes to shared file

**In Terminal 3:**
- The supervisor detects the number
- It verifies the calculation
- It asks you to approve: `Do you approve this sum? (yes/no):`
- Type `yes` if correct

**In Terminal 2:**
- Once Terminal 3 approves and sends decimals
- Terminal 2 automatically calculates decimal sum
- Reports completion

### Step 6: Repeat or Exit

All three apps ask if you want to process another number.

---

## Detailed Workflow

### Complete Execution Flow

```
TIME  TERMINAL 1           TERMINAL 2              TERMINAL 3
────  ──────────────────   ────────────────────    ──────────────────
T0    [RUNNING]            [WAITING]               [WAITING]
      "Enter a number:"

T1    User inputs: 5       [WAITING]               [WAITING]
      Calculate: 1+2+3+4+5 = 15
      Write to file

T2    [WAITING for T3]     [WAITING]               [MONITORING]
                                                   Reads: number=5, sum=15
                                                   Verifies: 15 is correct
                                                   "Approve? (yes/no):"

T3    [WAITING for T3]     [WAITING]               User types: yes
                                                   Generate decimals: [0.1..0.5]
                                                   Write to file

T4    [WAITING for T2]     [MONITORING]            [WAITING for T2]
                           Reads: decimals=[0.1..0.5]
                           Calculate: sum = 1.5
                           Write result & "finished"=true

T5    [COMPLETED]          [COMPLETED]            [MONITORING]
      Reports: "Workflow done"  Reports: "Task done" Sees "finished"=true
                                                     Reports: "Workflow done"

T6    "Another? (yes/no):"  "Another? (yes/no):"   "Another? (yes/no):"
      (Cycle can repeat)    (Waiting)              (Cycle can repeat)
```

---

## Shared File Format

The three apps communicate through `shared_state.json`:

```json
{
  "status": "approved_waiting_for_t2",
  "number": 5,
  "sum_integer": 15,
  "app2_ready": false,
  "app3_approved": true,
  "decimal_numbers": [
    0.1,
    0.2,
    0.3,
    0.4,
    0.5
  ],
  "sum_decimal": 1.5,
  "finished": true
}
```

### Field Descriptions

| Field | Set By | Purpose |
|-------|--------|---------|
| `number` | T1 | The input number from user |
| `sum_integer` | T1 | Sum of 1 to number |
| `status` | All | Current workflow status |
| `app3_approved` | T3 | Whether T3 approved the sum |
| `decimal_numbers` | T3 | Decimal numbers (0.1, 0.2, ...) for T2 |
| `sum_decimal` | T2 | Sum of decimal numbers |
| `finished` | T2 | Whether workflow is complete |

---

## Example Run

### Input: Number 3

```
TERMINAL 1:
  Enter a number: 3
  ✓ Calculated sum from 1 to 3
  📊 Sum = 6
  ⏳ Waiting for Terminal 3 to approve...

TERMINAL 3:
  ✅ Terminal 1 generated a sum
  VERIFICATION RESULT
  📊 Number provided: 3
  📊 Sum calculated: 6
  ✓ Expected sum: 6
  ✅ Sum is CORRECT!
  ❓ Do you approve this sum? (yes/no): yes
  ✅ You approved the sum!
  📋 Generating 3 decimal numbers...
     Generated: [0.1, 0.2, 0.3]

TERMINAL 2:
  ✅ Received 3 decimal numbers from Terminal 3
  📥 Received: [0.1, 0.2, 0.3]
  🔢 Calculating sum of decimal numbers...
     Sum = 0.6
  ✓ Sum calculated: 0.6

TERMINAL 3:
  ⏳ Waiting for Terminal 2 to process...
  ✅ Terminal 2 COMPLETED!
     Decimal Sum: 0.6
  ✅ ENTIRE WORKFLOW COMPLETED SUCCESSFULLY
```

---

## Troubleshooting

### Issue: "Shared file not found"

**Solution:** Make sure all three apps are in the same directory

```bash
ls -la
# Should see all three files:
# app1_generator.py
# app2_processor.py
# app3_supervisor.py
```

### Issue: "Timeout waiting for Terminal X"

**Solution:** Make sure all required terminals are running

```bash
# Check what's running:
ps aux | grep app
# Should see 3 processes (one for each terminal)
```

### Issue: "Decimal numbers not sent"

**Solution:** Make sure you approved the sum in Terminal 3

```
❓ Do you approve this sum? (yes/no): yes  ← Type 'yes'
```

### Issue: "App gets stuck"

**Solution:** Applications have built-in timeouts (2-5 minutes). Use Ctrl+C:

```bash
# Press Ctrl+C to stop the current app
# Then run it again
python3 app1_generator.py
```

### Issue: "shared_state.json is corrupted"

**Solution:** Delete it and restart all apps

```bash
rm shared_state.json
# Now restart Terminal 1, then Terminal 2, then Terminal 3
```

---

## Key Features

✅ **Independent Processes** - Each app runs separately in its own terminal
✅ **File-Based Communication** - Uses JSON file as shared storage
✅ **Synchronization** - Apps wait for each other automatically
✅ **User Approval** - Terminal 3 verifies and asks for user confirmation
✅ **Error Handling** - Timeouts and validation prevent deadlocks
✅ **Reusable** - Can process multiple numbers in sequence

---

## Technical Details

### Communication Method: **Method 1 - Shared File (JSON)**

- **Storage**: `shared_state.json` file on disk
- **Access**: All apps read/write to the same file
- **Speed**: Medium (disk I/O)
- **Reliability**: Good (persistent storage)
- **Best for**: Local development, same machine

### How It Works

1. **Terminal 1** writes data to `shared_state.json`
2. **Terminal 3** polls file every 1 second, reads data
3. **Terminal 3** writes approval/decimals back to file
4. **Terminal 2** polls file every 1 second, reads decimals
5. **Terminal 2** writes result back to file
6. All apps see changes within 1-2 seconds

### File Access Pattern

```
WRITE              READ
  ↓                ↓
T1 → File ← T3 ← File
              ↓
           decimals
             ↓
            File ← T2 ← READ
            ↓
          result
            ↓
           File
           READ ← T3
```

---

## Notes

- All three apps run in **separate Python processes**
- Data is shared via **file on disk** (not memory)
- This works because all three apps can access the **same filesystem**
- The apps use **polling** (check file every 1-2 seconds)
- Each app has **built-in timeouts** to prevent hanging

---

## Summary

| App | Terminal | Purpose | Input | Output |
|-----|----------|---------|-------|--------|
| 1 | Term 1 | Generate sum | Number | Sum |
| 3 | Term 3 | Supervise | Approval | Decimals |
| 2 | Term 2 | Process | Decimals | Decimal sum |

**Run order:** Start Terminal 2 → Terminal 3 → Terminal 1 (waiting mode first)

Happy testing! 🚀
