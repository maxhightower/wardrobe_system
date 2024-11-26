from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import os
import requests
import time
import re
import json
import sqlite3
from datetime import datetime




class amazon_image_scraper:
    def __init__(self, save_directory, db_path="wardrobe.db"):
        self.save_directory = save_directory
        self.db_path = db_path
        
        if not os.path.exists(save_directory):
            os.makedirs(save_directory)
            
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.implicitly_wait(10)
        
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        """Create tables to track scraped URLs and product details"""
        self.cursor.executescript('''
            CREATE TABLE IF NOT EXISTS scraped_urls (
                url_id INTEGER PRIMARY KEY AUTOINCREMENT,
                amazon_url TEXT UNIQUE,
                product_name TEXT,
                image_folder TEXT,
                product_details TEXT,  -- JSON string of product details
                date_scraped TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS product_features (
                feature_id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_id INTEGER,
                feature_text TEXT,
                FOREIGN KEY (url_id) REFERENCES scraped_urls (url_id)
            );
        ''')
        self.conn.commit()

    def clean_amazon_url(self, url):
        """Extract the essential part of Amazon URL (remove tracking parameters)"""
        # Extract the product ID (ASIN)
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        if asin_match:
            return f"https://www.amazon.com/dp/{asin_match.group(1)}"
        return url.split('?')[0]  # Fallback: just remove query parameters

    def check_url_exists(self, url):
        """Check if URL has already been scraped"""
        clean_url = self.clean_amazon_url(url)
        self.cursor.execute('''
            SELECT url_id, product_name, image_folder 
            FROM scraped_urls 
            WHERE amazon_url = ?
        ''', (clean_url,))
        return self.cursor.fetchone()

    def extract_product_details(self):
        """Extract details from 'About This Item' section"""
        details = []
        try:
            # Wait for the product details section
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div#feature-bullets"))
            )
            
            # Find all list items in the About This Item section
            detail_items = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "div#feature-bullets ul.a-unordered-list li span.a-list-item"
            )
            
            # Extract and clean each detail
            for item in detail_items:
                detail_text = item.text.strip()
                if detail_text and not detail_text.startswith("›"):  # Skip navigation arrows
                    details.append(detail_text)
                    
        except Exception as e:
            print(f"Error extracting product details: {str(e)}")
            
        return details

    def extract_additional_info(self):
        """Extract additional product information from other sections"""
        additional_info = {}
        try:
            # Try to get product specifications table
            try:
                product_info_section = self.driver.find_element(
                    By.ID, "productDetails_techSpec_section_1"
                )
                rows = product_info_section.find_elements(By.TAG_NAME, "tr")
                for row in rows:
                    try:
                        label = row.find_element(By.CLASS_NAME, "a-text-left").text.strip()
                        value = row.find_element(By.CLASS_NAME, "a-text-right").text.strip()
                        additional_info[label] = value
                    except:
                        continue
            except NoSuchElementException:
                pass

            # Try to get product information section
            try:
                info_section = self.driver.find_element(
                    By.ID, "productDetails_db_sections"
                )
                items = info_section.find_elements(By.CLASS_NAME, "a-spacing-top-base")
                for item in items:
                    try:
                        label = item.find_element(By.CLASS_NAME, "a-text-bold").text.strip()
                        value = item.find_element(By.CLASS_NAME, "a-text-right").text.strip()
                        additional_info[label] = value
                    except:
                        continue
            except NoSuchElementException:
                pass

        except Exception as e:
            print(f"Error extracting additional info: {str(e)}")

        return additional_info

    def scrape_product_page(self, url):
        """
        Scrape product images and details from Amazon URL
        Returns tuple: (success, message, image_path, details)
        """
        try:
            # Check if URL already exists
            existing_record = self.check_url_exists(url)
            if existing_record:
                return (False, "URL already scraped", existing_record[2], 
                       json.loads(existing_record[3]) if existing_record[3] else None)

            self.driver.get(url)
            
            # Wait for main elements
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "landingImage"))
            )
            
            # Get product title
            title_element = self.driver.find_element(By.ID, "productTitle")
            product_title = title_element.text.strip()
            safe_title = self._sanitize_filename(product_title)
            
            # Create product folder
            product_folder = os.path.join(self.save_directory, safe_title)
            if not os.path.exists(product_folder):
                os.makedirs(product_folder)
                print(f"Created folder: {product_folder}")
            
            # Get and save main image
            main_img = self.driver.find_element(By.ID, "landingImage")
            main_img_url = main_img.get_attribute('src')
            
            if main_img_url:
                image_path = os.path.join(product_folder, "main_image.jpg")
                response = requests.get(main_img_url)
                if response.status_code == 200:
                    with open(image_path, 'wb') as f:
                        f.write(response.content)
                    print(f"Saved main image to: {image_path}")
            
            # Extract product details and additional info
            details = self.extract_product_details()
            additional_info = self.extract_additional_info()
            
            # Combine all product information
            product_info = {
                "about_item": details,
                "additional_info": additional_info
            }
            
            # Save to database
            self.add_url_to_db(url, product_title, product_folder, product_info)
            
            return (True, "Successfully scraped product", product_folder, product_info)
            
        except TimeoutException:
            return (False, "Timeout waiting for page to load", None, None)
        except Exception as e:
            return (False, f"An error occurred: {str(e)}", None, None)

    def add_url_to_db(self, url, product_name, image_folder, product_info):
        """Add URL and product details to database"""
        clean_url = self.clean_amazon_url(url)
        self.cursor.execute('''
            INSERT INTO scraped_urls (amazon_url, product_name, image_folder, product_details)
            VALUES (?, ?, ?, ?)
        ''', (clean_url, product_name, image_folder, json.dumps(product_info)))
        
        url_id = self.cursor.lastrowid
        
        # Add individual features to features table
        for feature in product_info.get('about_item', []):
            self.cursor.execute('''
                INSERT INTO product_features (url_id, feature_text)
                VALUES (?, ?)
            ''', (url_id, feature))
        
        self.conn.commit()

    def get_product_details(self, url):
        """Retrieve stored product details for a URL"""
        clean_url = self.clean_amazon_url(url)
        self.cursor.execute('''
            SELECT product_details, product_features.feature_text
            FROM scraped_urls
            LEFT JOIN product_features ON scraped_urls.url_id = product_features.url_id
            WHERE amazon_url = ?
        ''', (clean_url,))
        
        rows = self.cursor.fetchall()
        if rows:
            details = json.loads(rows[0][0]) if rows[0][0] else {}
            features = [row[1] for row in rows if row[1]]
            return {'stored_details': details, 'features': features}
        return None

    # [Previous methods remain the same: clean_amazon_url, check_url_exists, etc.]


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


