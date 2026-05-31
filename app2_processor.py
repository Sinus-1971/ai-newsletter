#!/usr/bin/env python3
"""
TERMINAL 2: Decimal Processor
==============================

This application:
1. Waits for Terminal 3 to send decimal numbers
2. Calculates the sum of decimal numbers
3. Updates the shared file with result
4. Informs Terminal 3 that task is finished

Run this in Terminal 2:
    python3 app2_processor.py
"""

import json
import time
from pathlib import Path

# Shared file location (same as other apps)
SHARED_FILE = "shared_state.json"

def read_shared_file():
    """Read the shared state from JSON file"""
    try:
        with open(SHARED_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def write_shared_file(data):
    """Write state to JSON file"""
    with open(SHARED_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def wait_for_decimals():
    """Wait for Terminal 3 to provide decimal numbers"""
    print("\n⏳ Waiting for Terminal 3 to provide decimal numbers...")
    
    timeout = 0
    max_wait = 300  # Wait max 5 minutes
    
    while timeout < max_wait:
        state = read_shared_file()
        
        if state is None:
            print("⚠️  Shared file not found yet")
            time.sleep(2)
            timeout += 2
            continue
        
        # Check if decimals have been provided
        decimals = state.get("decimal_numbers", [])
        status = state.get("status", "")
        
        if decimals and len(decimals) > 0:
            print(f"\n✅ Received {len(decimals)} decimal numbers from Terminal 3")
            return decimals
        
        if status == "finished":
            # Already finished by another run
            print("⚠️  Already finished. Waiting for new data...")
            time.sleep(2)
            timeout += 2
            continue
        
        time.sleep(1)
        timeout += 1
        
        # Show status every 10 seconds
        if timeout % 10 == 0:
            print(f"   ⏳ Still waiting... ({timeout}s)")
    
    print(f"\n❌ Timeout waiting for Terminal 3")
    return None

def calculate_decimal_sum(decimals):
    """Calculate sum of decimal numbers"""
    if not decimals:
        return 0
    return sum(decimals)

def main():
    print("="*70)
    print("TERMINAL 2: Decimal Processor")
    print("="*70)
    
    # Check if shared file exists
    if not Path(SHARED_FILE).exists():
        print(f"\n⚠️  Shared file not found: {SHARED_FILE}")
        print("Make sure Terminal 1 has been run first")
        return
    
    print(f"✓ Using shared file: {SHARED_FILE}")
    
    while True:
        # Wait for decimal numbers
        decimals = wait_for_decimals()
        
        if decimals is None:
            print("\n❓ Try running again once Terminal 3 has provided decimals")
            again = input("Retry? (yes/no): ").lower()
            if again != 'yes' and again != 'y':
                print("\n👋 Terminal 2 closing...")
                return
            continue
        
        print(f"\n📥 Received decimal numbers: {decimals}")
        
        # Calculate sum
        decimal_sum = calculate_decimal_sum(decimals)
        
        print(f"\n🔢 Calculating sum of decimal numbers...")
        print(f"   Numbers: {decimals}")
        print(f"   Sum = {decimal_sum}")
        
        # Read current state
        state = read_shared_file()
        
        # Update with result
        state["sum_decimal"] = decimal_sum
        state["status"] = "processing_complete"
        state["finished"] = True
        
        # Write to shared file
        write_shared_file(state)
        
        print(f"\n✓ Sum calculated: {decimal_sum}")
        print(f"✓ Updated shared file: {SHARED_FILE}")
        print(f"📤 Notified Terminal 3 that task is finished")
        
        print("\n" + "="*70)
        print("TASK COMPLETED")
        print("="*70)
        print(f"Integer Sum (from Terminal 1): {state.get('sum_integer')}")
        print(f"Decimal Sum (from Terminal 2): {decimal_sum}")
        
        # Ask if user wants to process another batch
        again = input("\n❓ Process another batch? (yes/no): ").lower()
        if again != 'yes' and again != 'y':
            print("\n👋 Terminal 2 closing...")
            return

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Terminal 2 interrupted by user")
    except Exception as e:
        print(f"\n❌ Error in Terminal 2: {e}")
        import traceback
        traceback.print_exc()
