from sklearn.feature_extraction.text import TfidfVectorizer


class KeywordExtractor:

    def __init__(self):

        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=20
        )

    def extract(self, text):

        tfidf = self.vectorizer.fit_transform([text])

        words = self.vectorizer.get_feature_names_out()

        return list(words)
