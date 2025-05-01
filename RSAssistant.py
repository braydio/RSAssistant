@bot.command(name='tosell', help='Usage: `..addsell <ticker>` Add a ticker to the sell list.')
async def add_to_sell(ctx, ticker: str):
    ticker = ticker.upper()
    watch_list_manager.add_to_sell_list(ticker)
    await ctx.send(f'Added {ticker} to the sell list.')


@bot.command(name='nosell', help='Remove a ticker from the sell list. Usage: `..removesell <ticker>`')
async def remove_sell(ctx, ticker: str):
    ticker = ticker.upper()
    if watch_list_manager.remove_from_sell_list(ticker):
        await ctx.send(f'Removed {ticker} from the sell list.')
    else:
        await ctx.send(f'{ticker} was not in the sell list.')

@bot.command(name='selling', help='View the current sell list.')
async def view_sell_list(ctx):
    sell_list = watch_list_manager.get_sell_list()
    if not sell_list:
        await ctx.send('The sell list is empty.')
    else:
        embed = Embed(
            title='Sell List',
            description='Tickers flagged for selling',
            color=discord.Color.red,
        )
        for ticker, details in sell_list.items():
            added_on = details.get('added_on', 'N/A')
            embed.add_field(name=ticker, value=f'Added on: {added_on}', inline=False)
        await ctx.send(embed=embed)
