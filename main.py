import aiohttp
import asyncio
import os
import re
from datetime import datetime
from urllib.parse import quote
from typing import Dict, Any
import astrbot.api.message_components as Comp
from astrbot.api.message_components import Node, Plain, Image
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.all import AstrBotConfig
from astrbot.api import logger
from .method import TEMP_DIR, get_img_changeFormat

class NoGameFound(Exception):
    """找不到对应游戏的异常类"""
    pass

class NoOaIDFound(Exception):
    """oaid搜索结果异常异常类"""
    pass

class NoGidFound(Exception):
    """模糊搜索结果为空异常类"""
    pass

class VagueFoundError(Exception):
    """模糊搜索结果异常异常类"""
    pass

"""所有关于月幕Gal的API调用"""
class API_ym():
    def __init__(self):
        self.api = "https://www.ymgal.games"
        self.cid = "ymgal"
        self.c_sercet = "luna0327"

    async def gettoken(self):
        self.tapi = f"{self.api}/oauth/token?"
        self.data = {
            "grant_type":"client_credentials",
            "client_id":self.cid,
            "client_secret":self.c_sercet,
            "scope":"public"
    }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.tapi, data=self.data) as response:
                token = (await response.json())["access_token"]
                return token

    async def header(self,token):
        headers = {
            "Accept":"application/json;charset=utf-8",
            "Authorization":f"Bearer {token}",
            "version":"1",
    }
        return headers

    async def search_game(self, header, keyword:str, similarity:int) -> Dict[str,Any] :
        keyword = quote(keyword)
        similarity = similarity
        url = f"{self.api}/open/archive/search-game?mode=accurate&keyword={keyword}&similarity={similarity}"
        try:
            async with aiohttp.ClientSession(headers=header) as session:
                async with session.get(url) as response:
                    res = await response.json()
                    code = res["code"]

            #根据月幕提供的返回code判断返回处理
            if code == 0:
                 gamedata=res.get("data",{}).get("game",{})
                 result={
                    "id" : gamedata.get("gid", None),
                    "oaid" : gamedata.get("developerId", None),
                    "mainimg" : gamedata.get("mainImg","None"),
                    "name" : gamedata.get("name","None"),
                    "rd" : gamedata.get("releaseDate","None"),
                    "rest" : gamedata.get("restricted","None"),
                    "hc" : gamedata.get("haveChinese", False),
                    "cnname" : gamedata.get("chineseName","None"),
                    "intro" : gamedata.get("introduction","None")
                 }

            elif code!=0:
                if code == 614:
                    raise NoGameFound(
                        "参数错误，可能是根据关键词搜索不到游戏档案\n"
                        "在使用游戏简称、汉化名、外号等关键字无法查询到目标内容时，请使用 游戏原名（全名+标点+大小写无误）再次尝试，或者使用模糊查找"
                     )
                else:
                    raise Exception(f"返回错误，返回码code:{code}")

        except Exception:
            raise

        return {
            #ifoainfo用于控制请求会社信息只返回名字
            #返回header用于复用以查询gid对应的会社
            "if_oainfo":False,
            "result":result,
        }

    async def search_orgid_mergeinfo(
            self,header,
            gid:int,
            info:dict[str,Any]|None,
            if_oainfo:bool
        ) -> Dict[str,Any]:

        """搜索游戏机构详细信息;对搜索出来的游戏详情，进行将oaid匹配成对应的会社名的操作"""
        header = header
        gid = gid
        url = f"{self.api}/open/archive?orgId={gid}"
        try:
            async with aiohttp.ClientSession(headers=header) as session:
                async with session.get(url) as response:
                    res = await response.json()
                    code = res["code"]

                #根据月幕提供的返回code判断返回处理
                if code==0:

                    #if_oainfo判断是否只返回会社的名字信息
                    #通常为True，在进行将oaid匹配成对应的会社名的操作时if_oainfo会为False
                    if if_oainfo:
                        result_oa = {
                            "oaname":res.get("data",{}).get("org",{}).get("name", None),
                            "oacn":res.get("data",{}).get("org",{}).get("chineseName", None),
                            "istro":res.get("data",{}).get("org",{}).get("introduction", None),
                            "country":res.get("data",{}).get("org",{}).get("country", None)
                        }

                    #进行将匹配到的会社名返回到请求的信息集当中
                    else:
                        oa = {
                            "oaname":res.get("data",{}).get("org",{}).get("name", None),
                            "oacn":res.get("data",{}).get("org",{}).get("chineseName", None)
                        }
                        result_oa = info | {"oaname":oa.get("oaname"),"oacn":oa.get("oacn")}
                        del result_oa["oaid"]

                if code!=0:
                    result_oa = None
                    raise NoOaIDFound(f"返回错误，返回码code:{code}")

        except Exception:
            raise

        return result_oa

    async def vague_search_game(
            self,
            header,
            keyword:str,
            pageNum=1,
            pageSize=10
        ) -> Dict[str,Any] :

        """模糊查询游戏名 (即可能游戏列表查询，默认命中所请求到列表中的第一个)"""
        keyword = quote(keyword)
        url = f"https://www.ymgal.games/open/archive/search-game?mode=list&keyword={keyword}&pageNum={pageNum}&pageSize={pageSize}"
        try:
            async with aiohttp.ClientSession(headers=header) as session:
                async with session.get(url) as response:
                    res = await response.json()
                    code = res.get("code")

                #根据月幕提供的返回code判断返回处理
                if code == 0:
                    result = res.get("data",{}).get("result",{})
                    if result:
                        s_keyword = result[0].get("name", None)
                    else:
                        raise NoGidFound("模糊搜索无结果，请尝试更改关键词")

                if code != 0:
                    raise VagueFoundError(f"返回错误，返回码code:{code}")

        except Exception:
            raise

        return s_keyword

    def info_list(self,info:dict[str,Any]):
        """统一简介格式"""
        parg = (info.get("intro")).split("\n")
        if len(parg)<2:
            parg = (info.get("intro")).split("\n\n")
        pargs = []
        for p in parg:
            pattern = r"\s+"
            clean_p = f"{'':<7}{re.sub(pattern,'',p.strip())}"
            pargs.append(clean_p)
        intro = "\n".join(pargs)

        chain = (
            f"游戏名：{info.get('name')}（{info.get('cnname')}）\n"
            f"会社：{info.get('oaname')}（{info.get('oacn')}）\n"
            f"限制级：{'是' if info.get('rest') else '否' } \n"
            f"是否已有汉化：{'是' if info.get('hc') else '否' } \n"
            f"简介：\n{intro}"
         )
        return chain


@register("astrbot_plugin_galinfo", "Hxfrzc", "一个可以提供查询Galgame信息的插件，基于月幕Gal的api", "1.0.0")
class galgame(Star):
    def __init__(self, context: Context, config:AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.similarity = self.config.get("similarity", "default")
        self.m_c = self.config.get("message_components", "default")
        self.token_wait = self.config.get("token_refresh","defalut")
        self.if_fromfilesystem = self.config.get("if_fromfilessystem","defalut")
        self.ym = API_ym()

        #启动定时刷新token服务
        self.token_refresh_task = asyncio.create_task(self.token_refresh())
        logger.info(f"已启动定时刷新token，刷新间隔{self.token_wait}分钟")


    @filter.command("查询gal")
    async def search_galgame(self, event: AstrMessageEvent):
        """查询Gal信息，通过'/查询gal <游戏名>'触发"""
        cmd = event.message_str.split(maxsplit=1)
        if len(cmd)<2:
            yield event.plain_result("参数错误，请输入游戏")
            return

        keyword = cmd[1]
        token = self.token
        yield event.plain_result(f"正在搜索：{keyword}")
        try:
            header = await self.ym.header(token)
            info = await self.ym.search_game(header, keyword, self.similarity)

            #判断命中游戏信息中是否存在Oaid
            if info.get("result").get("oaid"):
                allinfo = await self.ym.search_orgid_mergeinfo(
                    header,
                    info.get("result").get("oaid"),
                    info.get("result"),
                    info.get("if_oainfo")
                )
            else:
                allinfo = info | {"oaname":None,"oacn":None}

            chains = self.ym.info_list(allinfo)
            #转换获取的webp格式视觉图为jpg
            imgpath = await get_img_changeFormat(
                allinfo.get("mainimg"),
                TEMP_DIR,
            )

            if "关闭" in self.if_fromfilesystem:
                with open(imgpath,"rb") as img:
                    img_p = img.read()

                    #判断是否使用消息转发
                if "开启" in self.m_c:
                    node = Node(
                        uin=3974507586,
                        name="玖玖瑠",
                        content=[
                            Image.fromBytes(img_p),
                            Plain(f"{chains}"),
                        ]
                    )
                    yield event.chain_result([node])

                else:
                    chain = [
                        Comp.Image.fromBytes(img_p),
                        Comp.Plain(f"{chains}")
                    ]
                    yield event.chain_result(chain)
            else:
                #判断是否使用消息转发
                if "开启" in self.m_c:
                    node = Node(
                        uin=3974507586,
                        name="玖玖瑠",
                        content=[
                            Image.fromFileSystem(imgpath),
                            Plain(f"{chains}"),
                        ]
                    )
                    yield event.chain_result([node])

                else:
                    chain = [
                        Comp.Image.fromFileSystem(imgpath),
                        Comp.Plain(f"{chains}")
                    ]
                    yield event.chain_result(chain)

            #清理缓存图片
            if os.path.exists(imgpath):
                try:
                    os.remove(imgpath)
                except Exception as e:
                    logger.error(f"删除转换后图片缓存文件失败，错误原因:{e}")

        except NoGameFound as e:
            yield event.plain_result(f"{e}")

        except Exception as e:
            logger.error(f"{type(e).__name__}:{e}")

    @filter.command("模糊查询gal")
    async def vague_search_galgame(self, event: AstrMessageEvent):
        """模糊查询Gal信息，通过'/模糊查询gal <游戏名>'触发"""
        cmd = event.message_str.split(maxsplit=1)
        if len(cmd)<2:
            yield event.plain_result("参数错误，请输入游戏")
            return

        keyword = cmd[1]
        token = self.token
        yield event.plain_result(f"正在模糊搜索：{keyword}")

        try:
            header = await self.ym.header(token)
            gal = await self.ym.vague_search_game(header,keyword)
            yield event.plain_result(f"已匹配最符合的一条：{gal}")
            try:
                info = await self.ym.search_game(header, gal, self.similarity)

                #判断命中游戏信息中是否存在Oaid
                if info.get("result").get("oaid"):
                    allinfo = await self.ym.search_orgid_mergeinfo(
                        header,
                        info.get("result").get("oaid"),
                        info.get("result"),
                        info.get("if_oainfo")
                    )
                else:
                    allinfo = info | {"oaname":None,"oacn":None}

                chains = self.ym.info_list(allinfo)

                #转换获取的webp格式视觉图为jpg
                imgpath = await get_img_changeFormat(
                    allinfo.get("mainimg"),
                    TEMP_DIR,
                )

                if "关闭" in self.if_fromfilesystem:
                    with open(imgpath,"rb") as img:
                        img_p = img.read()
                        #判断是否使用消息转发
                    if "开启" in self.m_c:
                        node = Node(
                            uin=3974507586,
                            name="玖玖瑠",
                            content=[
                                Image.fromBytes(img_p),
                                Plain(f"{chains}"),
                            ]
                        )
                        yield event.chain_result([node])

                    else:
                        chain = [
                            Comp.Image.fromBytes(img_p),
                            Comp.Plain(f"{chains}")
                        ]
                        yield event.chain_result(chain)
                else:
                    #判断是否使用消息转发
                    if "开启" in self.m_c:
                        node = Node(
                            uin=3974507586,
                            name="玖玖瑠",
                            content=[
                                Image.fromFileSystem(imgpath),
                                Plain(f"{chains}"),
                            ]
                        )
                        yield event.chain_result([node])

                    else:
                        chain = [
                            Comp.Image.fromFileSystem(imgpath),
                            Comp.Plain(f"{chains}")
                        ]
                        yield event.chain_result(chain)

                #清理缓存图片
                if os.path.exists(imgpath):
                    try:
                        os.remove(imgpath)
                    except Exception as e:
                        logger.error(f"删除转换后图片缓存文件失败，错误原因:{e}")

            except NoGameFound as e:
                yield event.plain_result(f"{e}")

            except Exception as e:
                logger.error(f"{type(e).__name__}:{e}")

        except NoGidFound as e:
            yield event.plain_result(f"{e}")
        except Exception as e:
            logger.error(f"{type(e).__name__}:{e}")

    async def token_refresh(self):
        """每隔一小时刷新一次token防止过期"""
        self.token = await self.ym.gettoken() #立刻获取一次token
        while True:
            try:
                #等待指定间隔触发
                interval = self.token_wait *60
                logger.info(f"[{datetime.now()}] 等待{self.token_wait}分钟后刷新 token...")
                await asyncio.sleep(interval)

                logger.info("开始尝试刷新token")
                try:
                    self.token = await self.ym.gettoken()
                    logger.info("刷新token成功")
                except Exception as e:
                    logger.error(f"刷新token失败，{type(e).__name__}:{e}")

            except Exception as e:
                logger.error(f"刷新token循环出错，{type(e).__name__}:{e}")

    async def terminate(self):
        """插件被卸载时的任务清理函数清理"""
        if not self.token_refresh_task.done():
            self.token_refresh_task.cancel()
            try:
                await self.token_refresh_task
            except asyncio.CancelledError:
                logger.info("自动刷新token已成功取消")
            except Exception as e:
                logger.error(f"自动刷新token取消失败，错误：{e}")
        pass
