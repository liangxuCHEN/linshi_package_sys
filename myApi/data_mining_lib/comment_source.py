# -*- coding: utf-8 -*-
import pymssql


def init_sql():
    conn = pymssql.connect(
        host='192.168.1.253:1433',
        user='bs-prt',
        password='123123',
        database='Collectiondb',
    )
    return conn


class Mssql:
    def __init__(self):
        self.host = '192.168.1.253:1433'
        self.user = 'bs-prt'
        self.pwd = '123123'
        self.db = 'Collectiondb'

    def __get_connect(self):
        if not self.db:
            raise (NameError, "do not have db information")
        self.conn = pymssql.connect(
            host=self.host,
            user=self.user,
            password=self.pwd,
            database=self.db,
            charset="utf8"
        )
        cur = self.conn.cursor()
        if not cur:
            raise (NameError, "Have some Error")
        else:
            return cur

    def exec_query(self, sql):
        """
         the query will return the list, example;
                ms = MSSQL(host="localhost",user="sa",pwd="123456",db="PythonWeiboStatistics")
                resList = ms.ExecQuery("SELECT id,NickName FROM WeiBoUser")
                for (id,NickName) in resList:
                    print str(id),NickName
        """
        cur = self.__get_connect()
        cur.execute(sql)
        res_list = cur.fetchall()

        # the db object must be closed
        self.conn.close()
        return res_list

    def exec_non_query(self, sql):
        """
            execute the query without return list, example：
            cur = self.__GetConnect()
            cur.execute(sql)
            self.conn.commit()
            self.conn.close()
        """
        cur = self.__get_connect()

        cur.execute(sql)

        self.conn.commit()
        self.conn.close()

    def exec_many_query(self, sql, param):
        """
            execute the query without return list, example：
            cur = self.__GetConnect()
            cur.execute(sql)
            self.conn.commit()
            self.conn.close()
        """
        cur = self.__get_connect()
        try:
            cur.executemany(sql, param)

            self.conn.commit()
        except Exception as e:
            self.conn.rollback()

        self.conn.close()


def get_all_data(creator):

    conn = Mssql()
    sql_text = "select * from T_Treasure_EvalCustomItem where Creator='%s'" % (creator.encode('utf8'))
    res = conn.exec_query(sql_text)
    if len(res) > 0:
        return res
    else:
        return False


def get_all_comment(item_id):

    conn = Mssql()

    sql_text = """
    select TOP 10 a.ItemName '项目名称', a.TreasureID '宝贝ID', a.TreasureName '宝贝名称',
    a.TreasureLink '宝贝链接', a.ShopName '商店名称',
    a.EvaluationScores '宝贝评分', a.Category_Name '类目', a.StyleName '风格',
    b.AuctionSku '规格描述', b.RateContent '买家评论'
    from T_Treasure_EvalCustomItem_Detail as a
    RIGHT JOIN V_Treasure_Evaluation as b
    on a.TreasureID = b.TreasureID
    WHERE a.ItemID={item_id}
    """.format(item_id=item_id)

    res = conn.exec_query(sql_text)

    return res

