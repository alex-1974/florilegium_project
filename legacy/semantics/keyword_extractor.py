import yake


class KeywordExtractor:

    def __init__(self, language="en", max_keywords=20):

        self.extractor = yake.KeywordExtractor(
            lan=language,
            n=3,
            top=max_keywords
        )

    def extract(self, text):

        kws = self.extractor.extract_keywords(text)

        return [kw for kw, score in kws]
