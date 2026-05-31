#!/usr/bin/env python3
"""
TERMINAL 1: Input Generator
============================

This application:
1. Asks user for a number
2. Calculates sum from 1 to that number
3. Writes result to shared JSON file
4. Waits for Terminal 3's approval to proceed

Run this in Terminal 1:
    python3 app1_generator.py
"""

import json
import time
import os
from pathlib import Path

# Shared file location (accessible by all 3 apps)
SHARED_FILE = "shared_state.json"

def initialize_shared_file():
    """Create or reset the shared file"""
    if not Path(SHARED_FILE).exists():
        data = {
            "status": "waiting_for_input",
            "number": None,
            "sum_integer": None,
            "app2_ready": False,
            "app3_approved": False,
            "decimal_numbers": [],
            "sum_decimal": None,
            "finished": False
        }
        write_shared_file(data)
        print(f"✓ Created shared file: {SHARED_FILE}")
    else:
        print(f"✓ Using existing shared file: {SHARED_FILE}")

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

def get_user_input():
    """Get number from user"""
    while True:
        try:
            num = int(input("\n📥 Enter a number: "))
            if num <= 0:
                print("❌ Please enter a positive number")
                continue
            return num
        except ValueError:
            print("❌ Invalid input. Please enter a whole number")

def calculate_sum(n):
    """Calculate sum from 1 to n"""
    return sum(range(1, n + 1))

def main():
    print("="*70)
    print("TERMINAL 1: Input Generator & Monitor")
    print("="*70)
    
    # Initialize shared file
    initialize_shared_file()
    
    while True:
        # Get number from user
        print("\n[TERMINAL 1] Waiting for user input...")
        number = get_user_input()
        
        # Calculate sum
        sum_integer = calculate_sum(number)
        
        # Read current state
        state = read_shared_file()
        
        # Update with new data
        state["number"] = number
        state["sum_integer"] = sum_integer
        state["status"] = "waiting_for_approval"
        state["app3_approved"] = False
        
        # Write to shared file
        write_shared_file(state)
        
        print(f"\n✓ Calculated sum from 1 to {number}")
        print(f"📊 Sum = {sum_integer}")
        print(f"📝 Written to shared file: {SHARED_FILE}")
        
        # Wait for Terminal 3 to approve
        print("\n⏳ Waiting for Terminal 3 to approve...")
        print("   (Terminal 3 should ask for confirmation)")
        
        timeout = 0
        max_wait = 120  # Wait max 2 minutes
        
        while timeout < max_wait:
            state = read_shared_file()
            
            if state.get("app3_approved"):
                print("\n✅ Terminal 3 APPROVED the number!")
                print(f"📤 Sending to Terminal 2 for processing...")
                
                # Mark that T1 has approved
                state["status"] = "approved_waiting_for_t2"
                write_shared_file(state)
                
                # Wait for Terminal 2 to complete
                print("\n⏳ Waiting for Terminal 2 to process decimal sum...")
                
                t2_timeout = 0
                while t2_timeout < max_wait:
                    state = read_shared_file()
                    
                    if state.get("finished"):
                        print("\n✅ WORKFLOW COMPLETED!")
                        print(f"   - Integer Sum: {state['sum_integer']}")
                        print(f"   - Decimal Sum: {state['sum_decimal']}")
                        print(f"\n📄 Final state saved in {SHARED_FILE}")
                        
                        # Ask if user wants to run again
                        again = input("\n❓ Process another number? (yes/no): ").lower()
                        if again != 'yes' and again != 'y':
                            print("\n👋 Terminal 1 closing...")
                            return
                        else:
                            break
                    
                    time.sleep(1)
                    t2_timeout += 1
                
                if t2_timeout >= max_wait:
                    print("\n❌ Timeout waiting for Terminal 2")
                    break
                
                break
            
            time.sleep(1)
            timeout += 1
            
            # Show status every 5 seconds
            if timeout % 5 == 0:
                print(f"   ⏳ Still waiting... ({timeout}s)")
        
        if timeout >= max_wait:
            print(f"\n❌ Timeout waiting for Terminal 3 approval")
            print("   Make sure Terminal 3 is running and confirms the number")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Terminal 1 interrupted by user")
    except Exception as e:
        print(f"\n❌ Error in Terminal 1: {e}")
        import traceback
        traceback.print_exc()
