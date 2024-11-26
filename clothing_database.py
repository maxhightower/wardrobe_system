# in this file we'll create the database of clothing items
from datetime import datetime
import sqlite3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import colorsys
from PIL import Image
import io
import requests
import os

class clothing_article:
    def __init__(self, name, brand, in_wardrobe, date_bought):
        self.name = name
        self.brand = brand
        self.in_wardrobe = in_wardrobe
        self.urls = []
        self.prices = []
        self.date_bought = date_bought
        self.colors = []
        self.tags = []
        self.text = []
        self.image_path = None  # Added to store local image path

class wardrobe_db:
    def __init__(self, db_path, image_folder):
        """Initialize the database and image storage"""
        self.db_path = db_path
        self.image_folder = image_folder
        if not os.path.exists(image_folder):
            os.makedirs(image_folder)
            
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.create_tables()
        
        # Initialize webdriver for Amazon scraping
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        self.driver = webdriver.Chrome(options=chrome_options)
        
    def create_tables(self):
        """Create necessary tables with additional fields for clothing_article properties"""
        self.cursor.executescript('''
            -- Modified clothing_items table to match clothing_article class
            CREATE TABLE IF NOT EXISTS clothing_items (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                brand TEXT,
                in_wardrobe INTEGER DEFAULT 1,
                date_bought TEXT,
                image_path TEXT,
                category_id INTEGER,
                color_id INTEGER,
                pattern_id INTEGER,
                material_id INTEGER,
                FOREIGN KEY (category_id) REFERENCES categories (category_id),
                FOREIGN KEY (color_id) REFERENCES colors (color_id),
                FOREIGN KEY (pattern_id) REFERENCES patterns (pattern_id),
                FOREIGN KEY (material_id) REFERENCES materials (material_id)
            );
            
            -- Store URLs for items
            CREATE TABLE IF NOT EXISTS item_urls (
                item_id INTEGER,
                url TEXT,
                price REAL,
                date_added TEXT,
                FOREIGN KEY (item_id) REFERENCES clothing_items (item_id)
            );
            
            -- Store extracted colors
            CREATE TABLE IF NOT EXISTS item_colors (
                item_id INTEGER,
                color_hex TEXT,
                percentage REAL,
                FOREIGN KEY (item_id) REFERENCES clothing_items (item_id)
            );
            
            -- Store tags and text
            CREATE TABLE IF NOT EXISTS item_tags (
                item_id INTEGER,
                tag TEXT,
                FOREIGN KEY (item_id) REFERENCES clothing_items (item_id)
            );
            
            -- Rest of the tables remain the same...
            [Previous table creation code for categories, colors, patterns, materials, etc.]
        ''')
        self.conn.commit()

    def extract_dominant_colors(self, image_path, num_colors=5):
        """Extract dominant colors from an image"""
        img = Image.open(image_path)
        img = img.resize((150, 150))  # Resize for faster processing
        pixels = list(img.getdata())
        
        # Convert to hex colors and count occurrences
        color_counts = {}
        for pixel in pixels:
            if len(pixel) > 3:  # Skip alpha channel if present
                pixel = pixel[:3]
            hex_color = '#{:02x}{:02x}{:02x}'.format(*pixel)
            color_counts[hex_color] = color_counts.get(hex_color, 0) + 1
            
        # Sort by frequency and get top colors
        total_pixels = len(pixels)
        dominant_colors = []
        for hex_color, count in sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:num_colors]:
            percentage = count / total_pixels
            dominant_colors.append((hex_color, percentage))
            
        return dominant_colors

    def scrape_amazon_product(self, url):
        """Scrape product details from Amazon URL"""
        try:
            self.driver.get(url)
            
            # Wait for product title
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "productTitle"))
            )
            
            # Extract product details
            title = self.driver.find_element(By.ID, "productTitle").text.strip()
            
            # Try to get brand
            try:
                brand = self.driver.find_element(By.ID, "bylineInfo").text.strip()
                brand = brand.replace("Visit the ", "").replace(" Store", "")
            except:
                brand = "Unknown"
                
            # Try to get price
            try:
                price_element = self.driver.find_element(By.CSS_SELECTOR, ".a-price .a-offscreen")
                price = float(price_element.get_attribute("textContent").replace("$", "").strip())
            except:
                price = None
                
            # Get main product image
            img_element = self.driver.find_element(By.ID, "landingImage")
            img_url = img_element.get_attribute('src')
            
            # Get product features for tags
            tags = []
            try:
                feature_bullets = self.driver.find_elements(By.CSS_SELECTOR, "#feature-bullets li")
                for bullet in feature_bullets:
                    tags.extend(bullet.text.strip().lower().split())
            except:
                pass
                
            return {
                'title': title,
                'brand': brand,
                'price': price,
                'img_url': img_url,
                'tags': tags,
                'source_url': url
            }
        except Exception as e:
            print(f"Error scraping Amazon product: {str(e)}")
            return None

    def add_from_clothing_article(self, article, amazon_url=None):
        """Add a clothing_article to the database, optionally scraping from Amazon"""
        try:
            # If Amazon URL provided, scrape additional details
            if amazon_url:
                amazon_data = self.scrape_amazon_product(amazon_url)
                if amazon_data:
                    # Update article with Amazon data
                    article.urls.append(amazon_data['source_url'])
                    if amazon_data['price']:
                        article.prices.append(amazon_data['price'])
                    article.tags.extend(amazon_data['tags'])
                    
                    # Download and save image
                    img_response = requests.get(amazon_data['img_url'])
                    if img_response.status_code == 200:
                        # Create unique filename
                        image_filename = f"{article.brand}_{article.name}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                        image_path = os.path.join(self.image_folder, image_filename)
                        
                        with open(image_path, 'wb') as f:
                            f.write(img_response.content)
                        article.image_path = image_path
                        
                        # Extract colors from image
                        article.colors = self.extract_dominant_colors(image_path)
            
            # Insert into clothing_items table
            self.cursor.execute('''
                INSERT INTO clothing_items (name, brand, in_wardrobe, date_bought, image_path)
                VALUES (?, ?, ?, ?, ?)
            ''', (article.name, article.brand, article.in_wardrobe, 
                  article.date_bought, article.image_path))
            
            item_id = self.cursor.lastrowid
            
            # Insert URLs and prices
            for i, url in enumerate(article.urls):
                price = article.prices[i] if i < len(article.prices) else None
                self.cursor.execute('''
                    INSERT INTO item_urls (item_id, url, price, date_added)
                    VALUES (?, ?, ?, ?)
                ''', (item_id, url, price, datetime.now().strftime('%Y-%m-%d')))
            
            # Insert colors
            for color_hex, percentage in article.colors:
                self.cursor.execute('''
                    INSERT INTO item_colors (item_id, color_hex, percentage)
                    VALUES (?, ?, ?)
                ''', (item_id, color_hex, percentage))
            
            # Insert tags
            for tag in article.tags:
                self.cursor.execute('''
                    INSERT INTO item_tags (item_id, tag)
                    VALUES (?, ?)
                ''', (item_id, tag))
            
            self.conn.commit()
            return item_id
            
        except Exception as e:
            print(f"Error adding clothing article: {str(e)}")
            self.conn.rollback()
            return None

    def close(self):
        """Clean up resources"""
        self.driver.quit()
        self.conn.close()

