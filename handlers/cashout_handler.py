class CashoutHandler:

    def __init__(
        self,
        bot,
        db,
        language,
        config
    ):

        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        
        