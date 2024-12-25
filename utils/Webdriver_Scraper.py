from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import logging

class StockSplitScraper:
    def __init__(self):
        self.symbols_and_links = []
        logging.basicConfig(level=logging.INFO)

    def get_week_dates(self):
        """Calculate the start (Sunday) and end (Saturday) dates of the week."""
        today = datetime.today()
        start_of_week = today - timedelta(days=today.weekday() + 1)  # Previous Sunday
        end_of_week = start_of_week + timedelta(days=6)  # Next Saturday
        return start_of_week.strftime('%Y-%m-%d'), end_of_week.strftime('%Y-%m-%d')

    def get_page_content(self, url):
        """Fetch the HTML content of the page."""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--log-level=3")
        options.add_experimental_option('excludeSwitches', ['enable-logging'])

        service = Service(EdgeChromiumDriverManager().install())
        driver = webdriver.Edge(service=service, options=options)

        try:
            logging.info(f"Accessing URL: {url}")
            driver.get(url)

            # Wait for the key element to load
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//a[@data-test='quoteLink']"))
            )
            logging.info("Page loaded successfully.")
            return driver.page_source
        except Exception as e:
            logging.error(f"Error loading page: {e}")
            raise
        finally:
            driver.quit()

    def parse_page_content(self, html):
        """Parse the page content to extract stock symbols and links."""
        logging.info("Parsing page content...")
        soup = BeautifulSoup(html, "html.parser")
        links = soup.find_all("a", {"data-test": "quoteLink"})
        
        if not links:
            logging.warning("No stock data found. Page structure might have changed.")
        
        self.symbols_and_links = [
            (link.text, 'https://finance.yahoo.com' + link["href"]) for link in links
        ]
        logging.info(f"Extracted {len(self.symbols_and_links)} stock symbols.")

    def search_ticker(self, ticker):
        """Search for a specific ticker."""
        return [
            (symbol, href) for symbol, href in self.symbols_and_links if symbol.lower() == ticker.lower()
        ]

    def save_html_for_debugging(self, html):
        """Save HTML content for debugging purposes."""
        with open("debug_page.html", "w", encoding="utf-8") as file:
            file.write(html)
        logging.info("Saved page source to debug_page.html.")

    async def run(self, ctx, mode, ticker=None, custom_dates=None):
        """
        Run the scraper in different modes:
        - search_ticker: Search for a specific ticker in stock split data.
        - weekly_report: Generate a weekly report of stock splits.
        - custom_report: Fetch stock splits for a custom date range (optional).
        """
        try:
            if mode == "search_ticker" and ticker:
                start_date, end_date = self.get_week_dates()
                url = f"https://finance.yahoo.com/calendar/splits?from={start_date}&to={end_date}&day={start_date}"
                html = self.get_page_content(url)
                self.save_html_for_debugging(html)  # Save for debugging
                self.parse_page_content(html)
                results = self.search_ticker(ticker)
                await self.send_results_to_discord(ctx, results)

            elif mode == "weekly_report":
                start_date, end_date = self.get_week_dates()
                all_results = []
                for day_offset in range(7):
                    current_date = datetime.strptime(start_date, '%Y-%m-%d') + timedelta(days=day_offset)
                    url = f"https://finance.yahoo.com/calendar/splits?from={start_date}&to={end_date}&day={current_date.strftime('%Y-%m-%d')}"
                    html = self.get_page_content(url)
                    self.save_html_for_debugging(html)  # Save for debugging
                    self.parse_page_content(html)
                    all_results.extend(self.symbols_and_links)

                await self.send_results_to_discord(ctx, all_results)

            elif mode == "custom_report" and custom_dates:
                start_date, end_date = custom_dates
                url = f"https://finance.yahoo.com/calendar/splits?from={start_date}&to={end_date}"
                html = self.get_page_content(url)
                self.save_html_for_debugging(html)  # Save for debugging
                self.parse_page_content(html)
                await self.send_results_to_discord(ctx, self.symbols_and_links)

            else:
                await ctx.send("Invalid mode or missing parameters. Use 'search_ticker', 'weekly_report', or 'custom_report'.")
        except Exception as e:
            logging.error(f"Error in StockSplitScraper.run: {e}")
            await ctx.send("An error occurred while processing your request.")
