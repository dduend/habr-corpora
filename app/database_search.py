import re
import sqlite3
from pymorphy3 import MorphAnalyzer


class ProcessingUserRequest:
    def __init__(self, user_request):
        """
        params:
        user_request: str - запрос пользователя
        """
        self.user_request = user_request
        self.morph = MorphAnalyzer(lang='ru')
        self.pos_tags = ('NOUN', 'ADJ', 'VERB', 'ADV', 'PROPN', 'INTJ', 'PRON',
                         'DET', 'NUM', 'CCONJ', 'SCONJ', 'ADP', 'PART', 'AUX')
        self.deprel_tags = ('acl', 'acl:relcl', 'advcl', 'advmod', 'amod',
                            'appos',
                            'aux', 'aux:pass', 'case', 'cc', 'ccomp', 'conj',
                            'cop', 'csubj', 'det', 'discourse', 'expl',
                            'fixed',
                            'flat', 'flat:name', 'iobj', 'list', 'mark',
                            'nmod',
                            'nsubj', 'nsubj:pass', 'nummod', 'nummod:gov',
                            'obj',
                            'obl', 'obl:agent', 'parataxis', 'root',
                            'vocative', 'xcomp')

    def parse_single_token(self, token):
        """Эта функция принимает однокомпонентный (без '+') токен
        (слово в кавычках/слово без кавычек/POS-тег/deprel-тег) и выдаёт
        кортеж, где первый элемент — "режим поиска", а второй — элемент, по
        которому будет осуществляться поиск."""
        if token in self.pos_tags:  # Поиск по части речи
            return 'only_pos', token
        elif token in self.deprel_tags:  # Поиск по синтаксической функции
            return 'only_deprel', token
        else:
            if all(char.isascii() for char in
                   token.strip('"').lower()):  # Проверяем, что введённое
                # пользователем слово — не полностью написанное латиницей (при
                # этом часть символов могут быть латинскими, например
                # "it-специалиста" — валидный запрос)
                error = 'Слово не может быть полностью написано латиницей! Если же вы имели в виду тег, то среди доступных его нет, проверьте инструкцию по поиску!'
                return error
            elif re.match(r'^"(.+)"$', token):  # Поиск точной формы
                return 'exact_wordform', token[1:-1].lower()
            else:  # Поиск любых грамматических форм
                lemma = self.morph.normal_forms(token)[0]
                return 'lemma', lemma

    def parse_multipart_token(self, token):
        """Эта функция принимает составной (с '+') токен (лемму с тегами — POS
        и/или deprel), разбивает по '+' и выдаёт кортеж, где первый элемент —
        "режим поиска", а последующие — элементы, по которым будет
        осуществляться поиск."""
        parts = token.split('+')
        if len(parts) > 3:
            error = 'В токене может быть макс. 3 элемента — лемма, POS-тег и deprel-тег!'
            return error
        else:
            lemma = parts[0].lower()
            if len(parts) == 2:
                if parts[1] in self.pos_tags:
                    return 'lemma+pos', lemma, parts[1]
                elif parts[1] in self.deprel_tags:
                    return 'lemma+deprel', lemma, parts[1]
                else:
                    error = 'Введённого тега среди доступных нет, проверьте инструкцию по поиску!'
                    return error
            else:
                if parts[1] in self.pos_tags and parts[2] in self.deprel_tags:
                    return 'lemma+pos+deprel', lemma, parts[1], parts[2]
                else:
                    if parts[1] not in self.pos_tags and parts[2] in \
                            self.deprel_tags:
                        error = 'Введённого POS-тега среди доступных нет, проверьте инструкцию по поиску!'
                        return error
                    elif parts[1] in self.pos_tags and parts[2] not in \
                            self.deprel_tags:
                        error = 'Введённого deprel-тега среди доступных нет, проверьте инструкцию по поиску!'
                        return error
                    elif parts[1] in self.deprel_tags and parts[2] in \
                            self.pos_tags:
                        error = 'Неверный порядок ввода тегов: необходимо ввести сперва POS-, а затем — deprel-тег!'
                        return error
                    else:
                        error = 'Введённых тегов среди доступных нет, проверьте инструкцию по поиску!'
                        return error

    def process_query(self):
        """Эта функция обрабатывает пользовательский запрос и выдаёт список
        кортежей для дальнейшего составления запросов к базе данных."""
        if re.search(r'[^a-zA-Zа-яА-ЯёЁ +:"]', self.user_request):
            value_error = 'В запросе присутствуют некорректные символы!'
            return value_error
        else:
            tokens = self.user_request.strip().split()
            if len(tokens) > 3:
                value_error = 'Длина запроса превышает 3 токена!'
                return value_error
            else:
                parsed_tokens_for_search = []
                for token in tokens:
                    if '+' in token:
                        result = self.parse_multipart_token(token)
                        if isinstance(result, tuple):
                            parsed_tokens_for_search.append(result)
                        else:
                            value_error = result
                            return value_error
                    else:
                        result = self.parse_single_token(token)
                        if isinstance(result, tuple):
                            parsed_tokens_for_search.append(result)
                        else:
                            value_error = result
                            return value_error
                return parsed_tokens_for_search


class GettingDataFromDB:
    def __init__(self, user_request, conn):
        """
        params:
        user_request: str - запрос пользователя
        conn: SQL connection - соединение с базой данных
        """
        self.user_request = user_request
        self.conn = conn
        self.cur = conn.cursor()

    def search_exact_wordform(self, token_info_tuple):
        """Эта функция принимает кортеж с информацией о токене, составляет
        SQL-запрос для поиска по конкретной словоформе и выдаёт список
        кортежей из id слов и id предложений из базы данных, подходящих под
        запрос."""
        query_condition = """
        SELECT word_id, sent_id
        FROM words
        WHERE token = ?
        """
        self.cur.execute(query_condition, (token_info_tuple[1],))
        output = self.cur.fetchall()
        return output

    def search_lemma(self, token_info_tuple):
        """Эта функция принимает кортеж с информацией о токене, составляет
        SQL-запрос для поиска любых грамматических форм и выдаёт список
        кортежей из id слов и id предложений из базы данных, подходящих под
        запрос."""
        query_condition = """
        SELECT word_id, sent_id
        FROM words
        WHERE lemma = ?
        """
        self.cur.execute(query_condition, (token_info_tuple[1],))
        output = self.cur.fetchall()
        return output

    def search_only_pos(self, token_info_tuple):
        """Эта функция принимает кортеж с информацией о токене, составляет
        SQL-запрос для поиска по части речи и выдаёт список кортежей из id
        слов и id предложений из базы данных, подходящих под запрос."""
        query_condition = """
        SELECT word_id, sent_id
        FROM words
        WHERE pos = ?
        """
        self.cur.execute(query_condition, (token_info_tuple[1],))
        output = self.cur.fetchall()
        return output

    def search_only_deprel(self, token_info_tuple):
        """Эта функция принимает кортеж с информацией о токене, составляет
        SQL-запрос для поиска по синтаксической функции и выдаёт список
        кортежей из id слов и id предложений из базы данных, подходящих под
        запрос."""
        query_condition = """
        SELECT word_id, sent_id
        FROM words
        WHERE deprel = ?
        """
        self.cur.execute(query_condition, (token_info_tuple[1],))
        output = self.cur.fetchall()
        return output

    def search_lemma_and_pos(self, token_info_tuple):
        """Эта функция принимает кортеж с информацией о токене, составляет
        SQL-запрос для поиска по лемме со специфицированной частью речи и
        выдаёт список кортежей из id слов и id предложений из базы данных,
        подходящих под запрос."""
        query_condition = """
        SELECT word_id, sent_id
        FROM words
        WHERE lemma = ? AND pos = ?
        """
        self.cur.execute(query_condition,
                         (token_info_tuple[1], token_info_tuple[2]))
        output = self.cur.fetchall()
        return output

    def search_lemma_and_deprel(self, token_info_tuple):
        """Эта функция принимает кортеж с информацией о токене, составляет
        SQL-запрос для поиска по лемме со специфицированной синтаксической
        функцией и выдаёт список кортежей из id слов и id предложений из базы
        данных, подходящих под запрос."""
        query_condition = """
        SELECT word_id, sent_id
        FROM words
        WHERE lemma = ? AND deprel = ?
        """
        self.cur.execute(query_condition,
                         (token_info_tuple[1], token_info_tuple[2]))
        output = self.cur.fetchall()
        return output

    def search_lemma_and_pos_and_deprel(self, token_info_tuple):
        """Эта функция принимает кортеж с информацией о токене, составляет
        SQL-запрос для поиска по лемме со специфицированными частью речи И
        синтаксической функцией и выдаёт список кортежей из id слов и id
        предложений из базы данных, подходящих под запрос."""
        query_condition = """
        SELECT word_id, sent_id
        FROM words
        WHERE lemma = ? AND pos = ? AND deprel = ?
        """
        self.cur.execute(query_condition, (token_info_tuple[1],
                                           token_info_tuple[2],
                                           token_info_tuple[3]))
        output = self.cur.fetchall()
        return output

    def get_output_for_next_token(self, output, next_token_info_tuple):
        """Эта функция принимает список кортежей из id слов и id предложений,
        в которых содержится первый токен, из базы данных, а также кортеж с
        информацией о следующем токене и выдаёт список кортежей из id слов и
        id предложений, в которых содержатся первый и следующий токены, из
        базы данных."""
        next_token_output = []
        if next_token_info_tuple[0] == 'exact_wordform':
            element = 'token'
        elif next_token_info_tuple[0] == 'only_pos':
            element = 'pos'
        elif next_token_info_tuple[0] == 'only_deprel':
            element = 'deprel'
        else:
            element = 'lemma'
            if next_token_info_tuple[0] == 'lemma+pos':
                element += ' = ? AND pos'
            elif next_token_info_tuple[0] == 'lemma+deprel':
                element += ' = ? AND deprel'
            elif next_token_info_tuple[0] == 'lemma+pos+deprel':
                element += ' = ? AND pos = ? AND deprel'
        next_token_query_condition = f"""
        SELECT word_id, sent_id
        FROM words
        WHERE {element} = ? AND word_id = ? AND sent_id = ?
        """
        for word_id, sent_id in output:
            next_word_id = word_id + 1
            if ' ' in element:
                elements = element.split(' = ? AND ')
                if len(elements) == 2:
                    self.cur.execute(next_token_query_condition,
                                     (next_token_info_tuple[1],
                                      next_token_info_tuple[2],
                                      next_word_id, sent_id))
                else:
                    self.cur.execute(next_token_query_condition,
                                     (next_token_info_tuple[1],
                                      next_token_info_tuple[2],
                                      next_token_info_tuple[3],
                                      next_word_id, sent_id))
            else:
                self.cur.execute(next_token_query_condition,
                                 (next_token_info_tuple[1], next_word_id,
                                  sent_id))
            result = self.cur.fetchone()
            if result:
                next_token_output.append(result)
        return next_token_output

    def get_sentences_idxs(self):
        """Эта функция принимает список кортежей с разбором 1-3 токенов, с
        помощью функций выше преобразует в SQL-запросы к базе данных и выдаёт
        список id предложений, подходящих под пользовательский запрос."""
        if self.user_request[0][0] == 'exact_wordform':
            output = self.search_exact_wordform(self.user_request[0])
        elif self.user_request[0][0] == 'lemma':
            output = self.search_lemma(self.user_request[0])
        elif self.user_request[0][0] == 'only_pos':
            output = self.search_only_pos(self.user_request[0])
        elif self.user_request[0][0] == 'only_deprel':
            output = self.search_only_deprel(self.user_request[0])
        elif self.user_request[0][0] == 'lemma+pos':
            output = self.search_lemma_and_pos(self.user_request[0])
        elif self.user_request[0][0] == 'lemma+deprel':
            output = self.search_lemma_and_deprel(self.user_request[0])
        else:
            output = self.search_lemma_and_pos_and_deprel(self.user_request[0])

        if output and len(self.user_request) > 1:
            next_token_output = \
                self.get_output_for_next_token(output, self.user_request[1])
            if len(self.user_request) == 3:
                next_token_output = self.get_output_for_next_token(
                    next_token_output, self.user_request[2])
                sentences_idxs = [result[1] for result in next_token_output]
                return sentences_idxs
            else:
                sentences_idxs = [result[1] for result in next_token_output]
                return sentences_idxs
        if output:
            output = [result[1] for result in output]
        return output

    def get_sentences_text_with_metainfo(self, idxs):
        """Эта функция принимает id предложений, подходящих под
        пользовательский запрос, составляет SQL-запрос с использованием JOIN
        для объединения данных из таблиц sentences и articles базы данных и
        выдаёт предложения с метаинформацией (автор, заголовок, ссылка на
        статью)."""
        if len(idxs) == 1:
            idxs = f'({idxs[0]})'
        else:
            idxs = tuple(idxs)
        sentences_with_metainfo_query_condition = f'''
            SELECT DISTINCT sentence, author, title, link FROM sentences
            JOIN articles ON sentences.article_id=articles.article_id 
            WHERE sentences.sent_id in {idxs}
        '''
        self.cur.execute(sentences_with_metainfo_query_condition)
        sentences_with_metainfo = self.cur.fetchall()
        return sentences_with_metainfo
