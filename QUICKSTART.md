# Quick Start Guide - Three Terminal Apps

## TL;DR - Just Run These Commands

### Step 1: Open 3 Terminal Windows

```
┌─────────────────────────────────┐
│ Terminal 1  │ Terminal 2 │ Terminal 3 │
└─────────────────────────────────┘
```

### Step 2: Run Applications in Order

**Terminal 2** (run first - waits):
```bash
python3 app2_processor.py
```

**Terminal 3** (run second - waits):
```bash
python3 app3_supervisor.py
```

**Terminal 1** (run third - gets user input):
```bash
python3 app1_generator.py
```

### Step 3: Follow the Prompts

**In Terminal 1:**
```
Enter a number: 5
```

**In Terminal 3:**
```
Do you approve this sum? (yes/no): yes
```

**That's it!** The apps will communicate automatically.

---

## What Each App Does

### Terminal 1 - Input Generator
```
1. Asks user for a number
2. Calculates sum from 1 to N
3. Sends result to shared file
4. Waits for Terminal 3 to approve
```

Example:
```
Enter a number: 5
✓ Calculated sum from 1 to 5
📊 Sum = 15
⏳ Waiting for Terminal 3 to approve...
✅ Terminal 3 APPROVED!
```

### Terminal 3 - Supervisor
```
1. Reads number from Terminal 1
2. Verifies the calculation is correct
3. Asks user to approve
4. Generates decimal numbers (0.1, 0.2, ..., 0.5)
5. Sends them to Terminal 2
6. Waits for Terminal 2 to complete
```

Example:
```
✅ Number: 5, Sum: 15 ✓ CORRECT!
Do you approve this sum? (yes/no): yes
Generated 5 decimals: [0.1, 0.2, 0.3, 0.4, 0.5]
Sent to Terminal 2 ✓
```

### Terminal 2 - Processor
```
1. Waits for decimals from Terminal 3
2. Calculates their sum
3. Reports completion
```

Example:
```
Waiting for Terminal 3...
✅ Received 5 decimal numbers
Calculating sum...
Sum = 1.5
Task finished ✓
```

---

## Data Flow

```
Terminal 1          Terminal 3              Terminal 2
    ↓                   ↓                       ↓
  Input            Supervisor              Processor
  (5)              (approve)               (calculate)
    │                   │                       │
    └───────→ shared_state.json ←───────────────┘
              (JSON file on disk)
```

---

## Full Workflow Example

**Input: 3**

```
Terminal 1:
  Enter a number: 3
  ✓ Sum = 6
  ⏳ Waiting...

Terminal 3:
  ✅ Got sum: 6
  Verify: 1+2+3 = 6 ✓
  CORRECT!
  Approve? yes
  Decimal: [0.1, 0.2, 0.3]
  → Send to T2

Terminal 2:
  ✅ Got [0.1, 0.2, 0.3]
  Sum = 0.6
  ✓ Done

Terminal 3:
  ✅ Workflow complete!
```

---

## What Gets Created

A file called `shared_state.json` is created:

```json
{
  "number": 5,
  "sum_integer": 15,
  "decimal_numbers": [0.1, 0.2, 0.3, 0.4, 0.5],
  "sum_decimal": 1.5,
  "finished": true
}
```

This file is where all three apps exchange data.

---

## Troubleshooting

### "Timeout waiting for Terminal 1"
→ Make sure Terminal 1 is running and providing input

### "Shared file not found"
→ Make sure all files are in the same directory

### "App is stuck"
→ Press Ctrl+C and try again

### "Getting wrong sum"
→ The app is working correctly! (It uses the formula: sum = n×(n+1)/2)

---

## How It Works Internally

### Communication Method: **Shared JSON File**

All three apps read and write to `shared_state.json`:

```
Terminal 1 WRITES:
  "number": 5
  "sum_integer": 15

Terminal 3 READS above, then WRITES:
  "app3_approved": true
  "decimal_numbers": [0.1, 0.2, 0.3, 0.4, 0.5]

Terminal 2 READS decimals, then WRITES:
  "sum_decimal": 1.5
  "finished": true

All terminals READ final result from file
```

**No shared memory, no network, no database** - just a simple JSON file that all three apps can read and write.

---

## Run Multiple Numbers

Each app asks at the end:
```
Process another number? (yes/no): yes
```

Just type `yes` to process another number without restarting!

---

## System Requirements

- Python 3.6+ (all three apps use standard library only)
- Same directory for all three files
- Three terminal windows/tabs
- That's it!

---

## Workflow States

```
START
  ↓
T1: Waiting for user input
  ↓
T1: Calculate sum
  ↓
T3: Wait for T1 to produce sum
  ↓
T3: Verify sum is correct
  ↓
T3: Ask user for approval
  ↓
T3: (User says YES) Generate decimals
  ↓
T2: Wait for decimals
  ↓
T2: Calculate decimal sum
  ↓
T3: Wait for T2 completion
  ↓
ALL: Report SUCCESS
  ↓
ASK: Another number? (yes/no)
  ↓
YES → Back to START
NO  → END
```

---

## Key Points

✅ **All three must be running** for it to work
✅ **Order matters** - Start T2, then T3, then T1
✅ **User interaction only in T1 and T3** - T2 is automatic
✅ **Communication via shared JSON file** - Check it in another terminal
✅ **Timeouts prevent hanging** - If something gets stuck, Ctrl+C and restart

---

## Example Full Run

```bash
# Terminal 1
$ python3 app1_generator.py
Enter a number: 7
✓ Calculated sum from 1 to 7
📊 Sum = 28
⏳ Waiting for Terminal 3 to approve...
✅ Terminal 3 APPROVED!
Process another number? (yes/no): no
👋 Terminal 1 closing...

# Terminal 3
$ python3 app3_supervisor.py
⏳ Waiting for Terminal 1 to generate...
✅ Terminal 1 generated sum = 28
VERIFICATION: 1+2+3+4+5+6+7 = 28 ✓
Do you approve? (yes/no): yes
Generated decimals: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
⏳ Waiting for Terminal 2...
✅ WORKFLOW COMPLETE! Decimal Sum = 2.8

# Terminal 2
$ python3 app2_processor.py
⏳ Waiting for decimals...
✅ Received 7 decimals
Sum = 2.8
Task finished!
```

---

## Next Steps

1. Download the three Python files
2. Put them in the same folder
3. Open three terminals in that folder
4. Run the apps in order (T2, T3, T1)
5. Follow prompts

That's all! The apps handle the rest automatically. 🚀
