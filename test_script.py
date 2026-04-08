import sys
import time
from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Go to local app
        page.goto("http://localhost:5000")
        time.sleep(1)
        
        # Login if needed
        try:
            page.fill('input[name="username"]', 'testme')
            page.fill('input[name="password"]', '123')
            page.click('button[type="submit"]')
            time.sleep(2)
        except Exception:
            pass # Maybe already logged in or handles differently
            
        print("Logged in. Navigating to friends...")
        # Evaluate js to show friends section
        page.evaluate("showSection('friends')")
        time.sleep(1)
        
        # Check initial rows
        rows_before = page.locator("#friendsTable tr").count()
        print(f"Rows before adding: {rows_before}")
        
        # Add friend
        page.fill('input[name="name"]', 'Automated Friend')
        page.fill('input[name="phone"]', '99999')
        page.click('button:has-text("Add Friend")')
        time.sleep(2)
        
        # Check rows right after adding
        rows_after_add = page.locator("#friendsTable tr").count()
        print(f"Rows after adding: {rows_after_add}")
        
        # Refresh the page
        print("Refreshing the page...")
        page.reload()
        time.sleep(2)
        
        page.evaluate("showSection('friends')")
        time.sleep(1)
        
        # Check rows after refresh
        rows_after_refresh = page.locator("#friendsTable tr").count()
        print(f"Rows after refresh: {rows_after_refresh}")
        
        # Print table HTML
        print(page.locator("#friendsTable").inner_html())
        
        browser.close()

if __name__ == "__main__":
    run()
