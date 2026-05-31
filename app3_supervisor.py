#!/usr/bin/env python3
"""
TERMINAL 3: Monitor & Supervisor
=================================

This application:
1. Monitors Terminal 1 for output (the sum)
2. Validates if the sum is correct
3. Asks user for approval
4. If approved, generates decimal numbers based on the integer
5. Sends decimals to Terminal 2 for processing
6. Monitors completion

Run this in Terminal 3:
    python3 app3_supervisor.py
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

def verify_sum(number, sum_value):
    """Verify if the sum is correct"""
    correct_sum = sum(range(1, number + 1))
    return sum_value == correct_sum

def generate_decimal_numbers(n):
    """
    Generate decimal numbers based on the integer.
    
    For example:
    - If n=5, generate: [0.1, 0.2, 0.3, 0.4, 0.5]
    - If n=10, generate: [0.1, 0.2, ..., 1.0]
    
    These will be sent to Terminal 2 for sum calculation
    """
    decimals = [round(i * 0.1, 1) for i in range(1, n + 1)]
    return decimals

def wait_for_input():
    """Wait for Terminal 1 to provide input"""
    print("\n⏳ Waiting for Terminal 1 to generate a sum...")
    
    previous_number = None
    timeout = 0
    max_wait = 300  # Wait max 5 minutes
    
    while timeout < max_wait:
        state = read_shared_file()
        
        if state is None:
            print("⚠️  Shared file not found yet")
            print("   Make sure Terminal 1 has been run first")
            time.sleep(2)
            timeout += 2
            continue
        
        # Check if Terminal 1 has provided a number
        number = state.get("number")
        sum_integer = state.get("sum_integer")
        status = state.get("status", "")
        
        if number is not None and sum_integer is not None:
            # New input from Terminal 1
            if number != previous_number:
                print(f"\n✅ Terminal 1 generated a sum")
                return number, sum_integer
            previous_number = number
        
        time.sleep(1)
        timeout += 1
        
        # Show status every 10 seconds
        if timeout % 10 == 0:
            print(f"   ⏳ Still waiting... ({timeout}s)")
    
    print(f"\n❌ Timeout waiting for Terminal 1")
    return None, None

def ask_user_approval(number, sum_value, is_correct):
    """Ask user to approve the generated sum"""
    print("\n" + "="*70)
    print("VERIFICATION RESULT")
    print("="*70)
    print(f"📊 Number provided: {number}")
    print(f"📊 Sum calculated: {sum_value}")
    print(f"✓ Expected sum: {sum(range(1, number + 1))}")
    
    if is_correct:
        print(f"✅ Sum is CORRECT!")
    else:
        print(f"❌ Sum is INCORRECT!")
    
    print("\n" + "="*70)
    
    while True:
        user_input = input("\n❓ Do you approve this sum? (yes/no): ").lower()
        if user_input in ['yes', 'y']:
            return True
        elif user_input in ['no', 'n']:
            return False
        else:
            print("❌ Please enter 'yes' or 'no'")

def main():
    print("="*70)
    print("TERMINAL 3: Monitor & Supervisor")
    print("="*70)
    
    # Check if shared file exists
    if not Path(SHARED_FILE).exists():
        print(f"\n⚠️  Shared file not found: {SHARED_FILE}")
        print("Make sure Terminal 1 has been run first")
        return
    
    print(f"✓ Using shared file: {SHARED_FILE}")
    
    while True:
        # Wait for Terminal 1 to provide input
        number, sum_integer = wait_for_input()
        
        if number is None:
            print("\n❓ Try running again once Terminal 1 has provided input")
            again = input("Retry? (yes/no): ").lower()
            if again != 'yes' and again != 'y':
                print("\n👋 Terminal 3 closing...")
                return
            continue
        
        # Verify the sum
        is_correct = verify_sum(number, sum_integer)
        
        # Ask user for approval
        approved = ask_user_approval(number, sum_integer, is_correct)
        
        if not approved:
            print("\n❌ You rejected the sum. Waiting for Terminal 1 to try again...")
            
            # Reset approval flag
            state = read_shared_file()
            state["app3_approved"] = False
            write_shared_file(state)
            
            time.sleep(2)
            continue
        
        print("\n✅ You approved the sum!")
        
        # Generate decimal numbers based on the integer
        print(f"\n📋 Generating {number} decimal numbers...")
        decimals = generate_decimal_numbers(number)
        print(f"   Generated: {decimals}")
        
        # Read current state
        state = read_shared_file()
        
        # Update with approval and decimal numbers
        state["app3_approved"] = True
        state["decimal_numbers"] = decimals
        state["status"] = "decimals_sent_to_t2"
        
        # Write to shared file
        write_shared_file(state)
        
        print(f"\n✓ Approved the sum")
        print(f"✓ Generated {len(decimals)} decimal numbers")
        print(f"✓ Sent to Terminal 2: {decimals}")
        print(f"📤 Updated shared file: {SHARED_FILE}")
        
        # Wait for Terminal 2 to complete
        print(f"\n⏳ Waiting for Terminal 2 to process decimal sum...")
        
        timeout = 0
        max_wait = 300
        
        while timeout < max_wait:
            state = read_shared_file()
            
            if state.get("finished"):
                print(f"\n✅ Terminal 2 COMPLETED!")
                print(f"   Decimal Sum: {state.get('sum_decimal')}")
                
                print("\n" + "="*70)
                print("✅ ENTIRE WORKFLOW COMPLETED SUCCESSFULLY")
                print("="*70)
                print(f"Integer (1 to {number}): {state.get('sum_integer')}")
                print(f"Decimals: {decimals}")
                print(f"Decimal Sum: {state.get('sum_decimal')}")
                
                # Ask if user wants to run again
                again = input("\n❓ Process another number? (yes/no): ").lower()
                if again != 'yes' and again != 'y':
                    print("\n👋 Terminal 3 closing...")
                    return
                else:
                    break
            
            time.sleep(1)
            timeout += 1
            
            # Show status every 10 seconds
            if timeout % 10 == 0:
                print(f"   ⏳ Still waiting... ({timeout}s)")
        
        if timeout >= max_wait:
            print(f"\n❌ Timeout waiting for Terminal 2")
            print("   Make sure Terminal 2 is running")
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Terminal 3 interrupted by user")
    except Exception as e:
        print(f"\n❌ Error in Terminal 3: {e}")
        import traceback
        traceback.print_exc()
