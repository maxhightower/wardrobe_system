from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import os
import requests
import time
import re

class amazon_image_scraper:
    def __init__(self, save_directory):
        """Initialize the scraper with Chrome webdriver and save location."""
        self.save_directory = save_directory
        
        # Create save directory if it doesn't exist
        if not os.path.exists(save_directory):
            os.makedirs(save_directory)
            
        # Set up Chrome options
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        # Initialize the webdriver
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.implicitly_wait(10)
    
    def _sanitize_filename(self, filename):
        """
        Convert filename to a safe string that can be used in file paths.
        """
        # Remove any characters that aren't alphanumeric, space, or hyphen
        safe_name = re.sub(r'[^a-zA-Z0-9\s-]', '', filename)
        # Replace spaces with underscores
        safe_name = safe_name.replace(' ', '_')
        # Reduce multiple underscores to single
        safe_name = re.sub(r'_{2,}', '_', safe_name)
        # Trim to reasonable length and strip any leading/trailing underscores
        safe_name = safe_name[:50].strip('_')
        return safe_name
    
    def scrape_product_page(self, url):
        """
        Scrape main product image from a specific Amazon product page
        
        Args:
            url (str): The full Amazon product URL
        """
        try:
            self.driver.get(url)
            
            # Wait for the main product image to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "landingImage"))
            )
            
            # Get product title for folder name
            try:
                title_element = self.driver.find_element(By.ID, "productTitle")
                product_title = title_element.text
                safe_title = self._sanitize_filename(product_title)
            except:
                safe_title = "unknown_product"
            
            # Create product-specific subfolder
            product_folder = os.path.join(self.save_directory, safe_title)
            if not os.path.exists(product_folder):
                os.makedirs(product_folder)
                print(f"Created folder: {product_folder}")
            
            # Get main product image
            main_img = self.driver.find_element(By.ID, "landingImage")
            main_img_url = main_img.get_attribute('src')
            if main_img_url:
                self._save_image(main_img_url, product_folder, "main_image")
            
            print(f"Image saved to: {product_folder}")
            
        except TimeoutException:
            print("Timeout waiting for page to load")
        except Exception as e:
            print(f"An error occurred: {str(e)}")
    
    def _save_image(self, img_url, folder, base_name):
        """Helper method to save an image to disk"""
        try:
            response = requests.get(img_url)
            if response.status_code == 200:
                # Determine file extension (usually .jpg)
                ext = '.jpg'  # Default to .jpg
                if 'content-type' in response.headers:
                    if 'png' in response.headers['content-type']:
                        ext = '.png'
                    elif 'gif' in response.headers['content-type']:
                        ext = '.gif'
                
                filepath = os.path.join(folder, f"{base_name}{ext}")
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                print(f"Saved: {filepath}")
        except Exception as e:
            print(f"Error saving image {base_name}: {str(e)}")
    
    def close(self):
        """Close the webdriver."""
        self.driver.quit()