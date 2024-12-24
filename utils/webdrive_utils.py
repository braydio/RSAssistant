from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import discord
from discord.ext import commands


class StockSplitScraper:
    def __init__(self):
        self.symbols_and_links = []

    def get_week_dates(self):
        """Calculate the start (Sunday) and end (Saturday) dates of the week."""
        today = datetime.today()
        days_ahead = 6 - today.weekday()  # Days until next Sunday
        if days_ahead < 0:
            days_ahead += 7
        sunday = today + timedelta(days=days_ahead)
        saturday = sunday + timedelta(days=6)
        return sunday.strftime('%Y-%m-%d'), saturday.strftime('%Y-%m-%d')

    def get_page_content(self, url):
        """Fetch the HTML content of the page."""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--log-level=3")
        options.add_experimental_option('excludeSwitches', ['enable-logging'])

        # Use webdriver-manager to automatically manage the Edge WebDriver
        driver = webdriver.Edge(EdgeChromiumDriverManager().install(), options=options)
        try:
            driver.get(url)
            driver.implicitly_wait(10)
            time.sleep(2)
            return driver.page_source
        finally:
            driver.quit()

    def parse_page_content(self, html):
        """Parse the page content to extract stock symbols and links."""
        soup = BeautifulSoup(html, "html.parser")
        links = soup.find_all("a", {"data-test": "quoteLink"})
        for link in links:
            symbol = link.text
            href = 'https://finance.yahoo.com' + link["href"]
            self.symbols_and_links.append((symbol, href))

    def search_ticker(self, ticker):
        """Search for a specific ticker."""
        return [(symbol, href) for symbol, href in self.symbols_and_links if symbol.lower() == ticker.lower()]

    async def send_results_to_discord(self, ctx, results):
        """Send results as a Discord message."""
        if results:
            for symbol, href in results:
                await ctx.send(f"{symbol}: {href}")
        else:
            await ctx.send("No results found for the specified ticker.")

    async def run(self, ctx, mode, ticker=None):
        """Run the scraper in different modes."""
        if mode == "search_ticker" and ticker:
            start_date, end_date = self.get_week_dates()
            url = f"https://finance.yahoo.com/calendar/splits?from={start_date}&to={end_date}&day={start_date}"
            html = self.get_page_content(url)
            self.parse_page_content(html)
            results = self.search_ticker(ticker)
            await self.send_results_to_discord(ctx, results)
        elif mode == "weekly_report":
            all_symbols_and_links = []
            start_date, end_date = self.get_week_dates()
            for day in range(7):
                self.symbols_and_links = []
                date = datetime.strptime(start_date, '%Y-%m-%d') + timedelta(days=day)
                date_str = date.strftime('%Y-%m-%d')
                url = f"https://finance.yahoo.com/calendar/splits?from={start_date}&to={end_date}&day={date_str}"
                html = self.get_page_content(url)
                self.parse_page_content(html)
                all_symbols_and_links.extend(self.symbols_and_links)

            await self.send_results_to_discord(ctx, all_symbols_and_links)
        else:
            await ctx.send("Invalid mode or missing parameters.")


