The below items are from the current RSAssistant.py main file.
The file is large and bulky and hard to navigate
To remedy this, we will do some cleanup.
Looking to create a definite Class to handle all below logic and import from external file.

The below functions may be stale, so be sure to pull updated code from RSAssistant.py upon creation.

```

@bot.command(name="todiscord", help="Prints text file one line at a time")
async def print_by_line(ctx):
    """Prints contents of a file to Discord, one line at a time."""
    await print_to_discord(ctx)

@bot.command(
    name="addmap",
    help="Adds mapping details for an account to the Account Mappings file.",
)
async def add_account_mappings_command(
    ctx, brokerage: str, broker_no: str, account: str, nickname: str
):
    try:
        await add_account_mappings(ctx, brokerage, broker_no, account, nickname)
    except Exception as e:
        logger.error(f"Error adding account mapping: {e}")
        await ctx.send("An error occurred while adding the mapping.")

@bot.command(name="loadmap", help="Maps accounts from Account Details excel sheet")
async def load_account_mappings_command(ctx):
    """Maps account details from the Excel sheet to JSON."""
    try:
        await ctx.send("Mapping account details...")
        await index_account_details(ctx)
        await ctx.send(
            "Mapping complete.\n Run `..loadlog` to save mapped accounts to the excel logger."
        )
    except Exception as e:
        await ctx.send(f"An error occurred during update: {str(e)}")


@bot.command(name="loadlog", help="Updates excel log with mapped accounts")
async def update_log_with_mappings(ctx):
    """Updates the Excel log with mapped accounts."""
    try:
        await ctx.send("Updating log with mapped accounts...")
        await map_accounts_in_excel_log(ctx)
        await ctx.send("Complete.")
    except Exception as e:
        await ctx.send(f"An error occurred during update: {str(e)}")

```

Review for creating a utility, or class method.
