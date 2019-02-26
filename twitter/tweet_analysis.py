import tweepy
from core4.queue.job import CoreJob
from nltk.tokenize.casual import TweetTokenizer
from pattern.text.de import parsetree


class TweetLoader(CoreJob):
    """
    Loads all tweets coming from a given region or place and saves them into
    a mongodb collection.
    The tweets are retrieved via the Twitter Search API in no particular
    order, this means the latest tweets are not guaranteed.
    """
    author = 'adi'
    schedule = '0,20,40 * * * *'  # runs every 20 minutes

    def execute(self, *args, **kwargs):
        consumer_key = self.config.twitter.api.consumer_key
        consumer_secret = self.config.twitter.api.consumer_secret
        access_token = self.config.twitter.api.access_token
        access_token_secret = self.config.twitter.api.access_token_secret

        self.set_source('Twitter Search API')
        tweet_coll = self.config.twitter.api.tweet_coll

        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_token_secret)

        api = tweepy.API(
            auth)

        # this code was run once to get the place id, afterwards I saved it to
        # prevent getting rate limited on a part that isn't going to change

        # place = api.geo_search(query='Germany', granularity="country")
        # place_id = place[0].id
        place_id = 'fdcd221ac44fa326'

        # get as many tweets as you can before being rate limited and then end
        # the job
        try:
            while True:
                tweets = api.search(q="place:%s" % place_id,
                                    lang='de',
                                    count='100',
                                    tweet_mode='extended')
                for tweet in tweets:
                    tweet_dict = tweet._json
                    tweet_dict['_id'] = tweet_dict['id_str']
                    tweet_coll.find_one_and_update({'_id': tweet_dict['_id']},
                                                   {'$setOnInsert': tweet_dict},
                                                   upsert=True)
        except tweepy.RateLimitError:
            pass  # let the job end normally


class TweetPOSTagger(CoreJob):
    """
    Tokenizes and POS tags all available tweets in the tweets
    collection and writes them to the mongo collection grouped by word
    lemma, word type and chunk type.
    The tokenizer strips the twitter handles.
    The POS tagger used is for german.
    """
    author = 'adi'

    def execute(self, *args, **kwargs):
        tweet_coll = self.config.twitter.api.tweet_coll
        pos_processed_strip_coll = \
            self.config.twitter.pos.pos_processed_strip_coll
        self.set_source('POS Tagger')

        cur = tweet_coll.find()
        for i, doc in enumerate(cur):
            tokenizer = TweetTokenizer(strip_handles=True)
            tmp_string = tokenizer.tokenize(doc['full_text'])
            s = [' '.join(tmp_string)]
            tokenized_string = [isinstance(s, str) and s.split(" ") or s for s
                                in s]
            if tokenized_string:
                try:
                    sentence_list = parsetree(tokenized_string,
                                              tokenize=False,
                                              lemmata=True)
                except TypeError:
                    continue

                for sentence in sentence_list:
                    for chunk in sentence.chunks:
                        for word in chunk.words:
                            dic = {}
                            dic['_id'] = '{}_{}_{}'.format(word.lemma,
                                                           word.type,
                                                           chunk.type)
                            dic['word'] = word.string
                            dic['word_category'] = word.type
                            dic['word_lemma'] = word.lemma
                            dic['chunk_category'] = chunk.type
                            dic['chunk_lemmata'] = chunk.lemmata
                            pos_processed_strip_coll.update_one(
                                filter={'_id': dic['_id']},
                                update={'$setOnInsert': dic},
                                upsert=True)
                            pos_processed_strip_coll.update_one(
                                filter={'_id': dic['_id']},
                                update={'$inc': {'count': 1}},
                                upsert=True)
                            # TODO: re-enable once the bug is fixed.
                            # requests.append(UpdateOne(filter={'_id':
                            # pos_dic['_id']}, update={'$set': pos_dic},
                            # upsert=True))
                            # requests.append(UpdateOne(filter={'_id':
                            # pos_dic['_id']}, update={'$inc': {'count': 1}},
                            # upsert=True))

            self.progress(i / cur.count())
        # TODO: re-enable once the bug is fixed
        # pos_unprocessed_coll.bulk_write(requests)


if __name__ == '__main__':
    from core4.queue.helper.functool import execute

    execute(TweetPOSTagger)
