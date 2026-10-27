class Entry:
    def normalize(self, archive, logger):
        self.name = self.title
        super().normalize(archive, logger)
