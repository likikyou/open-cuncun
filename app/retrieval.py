"""
向量检索模块
负责 Embedding 生成、ChromaDB 集合管理、长期记忆与外脑知识库检索
"""

import os
import re
import threading
import chromadb
from .config import Config
from .logger import logger
from fastembed import TextEmbedding

# --- FastEmbed 初始化 (单例模式) ---
_embedding_model = None
_embedding_model_lock = threading.Lock()
clients = {}


def get_embedding_model():
    """按需加载本地 Embedding 模型"""
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    with _embedding_model_lock:
        if _embedding_model is not None:
            return _embedding_model

        try:
            # 选用高度优化的 BAAI/bge-small-zh-v1.5 (512 维)
            # 首次运行时会自动从 ~/.cache/fastembed 下载 (约 100MB)
            logger.info(
                "⏳ FastEmbed 首次调用采用懒加载；若本机无缓存，将从 ~/.cache/fastembed 下载模型"
                " (约 100MB)，并阻塞当前这一次检索/语音匹配请求"
            )
            _embedding_model = TextEmbedding(model_name="BAAI/bge-small-zh-v1.5")
            logger.info(
                "✅ 本地向量化引擎 (FastEmbed: BGE-small) 初始化成功，后续请求将复用本地缓存"
            )
        except Exception as e:
            logger.error(f"❌ 本地向量化引擎加载失败（首次下载或本地缓存初始化异常）: {e}")
    return _embedding_model


def get_embedding(text):
    """获取单条文本向量 (本地 CPU 推理, BGE-small 512维)"""
    model = get_embedding_model()
    if not model or not text:
        return None
    try:
        # model.embed 返回的是生成器，转为 list
        embeddings = list(model.embed([text]))
        if embeddings:
            return embeddings[0].tolist()
    except Exception as e:
        logger.error(f"本地向量化异常: {e}")
    return None


def get_embeddings_batch(texts):
    """批量获取多个文本的向量 (本地推理, BGE-small 512维)"""
    model = get_embedding_model()
    if not model or not texts:
        return []
    try:
        embeddings = list(model.embed(texts))
        return [e.tolist() for e in embeddings]
    except Exception as e:
        logger.error(f"本地批量向量化异常: {e}")
        return []


# --- 初始化向量库 ---
audio_collection = None
bio_collection = None
knowledge_collection = None
persona_collection = None
user_profile_collection = None
relationship_collection = None


def _query_collection_documents(
    collection,
    query_text: str,
    n_results: int = 3,
    distance_threshold: float = 1.0,
    where: dict | None = None,
) -> list[str]:
    """通用的 Chroma 文本检索，返回过滤后的 documents 列表。"""
    if collection is None or not query_text:
        return []

    vec = get_embedding(query_text)
    if not vec:
        return []

    try:
        query_kwargs = {"query_embeddings": [vec], "n_results": n_results}
        if where:
            query_kwargs["where"] = where
        res = collection.query(**query_kwargs)
        docs = res.get("documents", [[]])[0]
        distances = res.get("distances", [[]])[0]
        if not docs:
            return []
        return [
            doc
            for i, doc in enumerate(docs)
            if i < len(distances) and distances[i] < distance_threshold
        ]
    except Exception as e:
        logger.warning(f"⚠️ 向量集合查询异常: {e}")
        return []


def _format_memory_block(title: str, docs: list[str]) -> str:
    if not docs:
        return ""
    return f"\n【{title}】\n" + "\n".join(f"- {doc}" for doc in docs) + "\n"


def _compact_persona_doc(doc: str, limit: int = 80) -> str:
    """把人设底稿压成更像内心提示的短句，避免原文生硬灌入上下文。"""
    if not doc:
        return ""

    text = re.sub(r"^##\s*", "", doc.strip())
    text = re.sub(r"^[一二三四五六七八九十]+、\s*", "", text)
    text = re.sub(r"^[^：:]{0,20}[：:]\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    for sep in ("。", "！", "？"):
        idx = text.find(sep)
        if 0 < idx <= limit:
            return text[: idx + 1]

    if len(text) <= limit:
        return text
    return text[:limit].rstrip("，,；;：: ") + "..."


def get_persona_memory(query_text: str, n_results: int = 3, distance_threshold: float = 1.2) -> str:
    """从 companion_persona 检索人设底稿。"""
    docs = _query_collection_documents(
        persona_collection,
        query_text,
        n_results=n_results,
        distance_threshold=distance_threshold,
    )
    compact_docs = [_compact_persona_doc(doc) for doc in docs if doc]
    return _format_memory_block("角色底色与自我认知", compact_docs)


def get_user_profile_memory(
    query_text: str, user_id: str, n_results: int = 3, distance_threshold: float = 1.2
) -> str:
    """从 companion_user_profile 检索用户稳定画像。"""
    docs = _query_collection_documents(
        user_profile_collection,
        query_text,
        n_results=n_results,
        distance_threshold=distance_threshold,
        where={"user_id": user_id} if user_id else None,
    )
    return _format_memory_block("关于他的稳定印象", docs)


def get_relationship_memory(
    query_text: str, user_id: str, n_results: int = 3, distance_threshold: float = 1.2
) -> str:
    """从 companion_relationship 检索关系层洞察。"""
    docs = _query_collection_documents(
        relationship_collection,
        query_text,
        n_results=n_results,
        distance_threshold=distance_threshold,
        where={"user_id": user_id} if user_id else None,
    )
    return _format_memory_block("你们之间慢慢形成的默契", docs)


try:
    # 统一管理 ChromaDB 客户端，避免重复初始化
    # 注意：
    # 1. data/db_local 下的 Chroma 数据是本地资产，不会随代码仓库同步。
    # 2. GitHub 中能保留的是集合结构与迁移脚本，不能保留这里面的真实向量内容。
    # 3. 新机器拉代码后，如果想恢复当前这套 persona/user_profile/relationship 分层，
    #    需要先准备好本地 MEMORY_PATH，再按需执行 scripts/migrate_memory_layers.py。
    os.makedirs(Config.MEMORY_PATH, exist_ok=True)
    # 复用已创建的客户端，避免重复连接
    if Config.MEMORY_PATH not in clients:
        clients[Config.MEMORY_PATH] = chromadb.PersistentClient(path=Config.MEMORY_PATH)
    client_memory = clients[Config.MEMORY_PATH]
    bio_collection = client_memory.get_or_create_collection(name="companion_bio")
    knowledge_collection = client_memory.get_or_create_collection(name="companion_knowledge")
    audio_collection = client_memory.get_or_create_collection(name="companion_audio")
    persona_collection = client_memory.get_or_create_collection(name="companion_persona")
    user_profile_collection = client_memory.get_or_create_collection(name="companion_user_profile")
    relationship_collection = client_memory.get_or_create_collection(name="companion_relationship")
    logger.info(f"✅ 长期记忆与外脑知识库已加载 (目录: {Config.MEMORY_PATH})")
except Exception as e:
    logger.warning(f"向量库加载警告: {e}")


def get_long_term_memory(
    user_text: str, n_results: int = 3, distance_threshold: float = 1.0, user_id: str = ""
) -> str:
    """从 companion_bio 检索长期记忆事实（RAG）

    Args:
        user_text: 用户输入文本
        n_results: 最多检索条数
        distance_threshold: 余弦距离阈值，越小越严格（默认 1.0）
                           - < 0.8: 高度相关
                           - 0.8-1.0: 中度相关
                           - > 1.0: 不太相关，不返回
        user_id: 用户ID，用于过滤只返回该用户的记忆
    """
    if bio_collection is None:
        return ""
    try:
        vec = get_embedding(user_text)
        if not vec:
            return ""

        query_kwargs = {"query_embeddings": [vec], "n_results": n_results}
        if user_id:
            query_kwargs["where"] = {"user_id": user_id}
        res = bio_collection.query(**query_kwargs)
        docs = res.get("documents", [[]])[0]
        distances = res.get("distances", [[]])[0]
        metadatas = res.get("metadatas", [[]])[0]

        if not docs:
            return ""

        relevant_memories = []
        for i, doc in enumerate(docs):
            meta = metadatas[i] if i < len(metadatas) and isinstance(metadatas[i], dict) else {}
            source = meta.get("source", "")
            # companion_bio 目前同时承载历史底稿与仿生记忆；长期记忆层应排除仿生反思/整合结果，
            # 避免与 retrieve_bionic_memories() 在同一轮上下文里重复注入。
            if source in {"bionic_reflection", "bionic_consolidation"}:
                continue
            if distances[i] < distance_threshold:
                relevant_memories.append(f"- {doc}")

        if not relevant_memories:
            return ""

        memories_text = "\n".join(relevant_memories)
        logger.info(
            f"🧠 检索到 {len(relevant_memories)} 条相关背景记忆 (阈值<{distance_threshold})"
        )
        return f"\n【检测到相关背景记忆】\n{memories_text}\n"
    except Exception as e:
        logger.error(f"长期记忆检索失败: {e}")
    return ""


def get_knowledge_memory(query: str, top_k: int = 2) -> str:
    """从 companion_knowledge 检索主人灌输的外脑知识"""
    if not knowledge_collection:
        return ""
    try:
        query_emb = get_embedding(query)
        if not query_emb:
            return ""

        results = knowledge_collection.query(query_embeddings=[query_emb], n_results=top_k)

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not docs:
            return ""

        knowledge_pieces = []
        for i, doc in enumerate(docs):
            if distances[i] < 1.2:  # 余弦距离阈值（越小越准确）
                source = metas[i].get("source", "未知文档") if metas else "未知文档"
                knowledge_pieces.append(f"[源自: {source}]\n{doc}")

        if not knowledge_pieces:
            return ""

        return "\n\n".join(knowledge_pieces)
    except Exception as e:
        logger.warning(f"⚠️ 外脑知识检索异常: {e}")
        return ""
