warning: in the working copy of 'src\graph\client.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of '.sandbox\t0.7\src\graph\client.py', LF will be replaced by CRLF the next time Git touches it
[1mdiff --git "a/src\\graph\\client.py" "b/.sandbox\\t0.7\\src\\graph\\client.py"[m
[1mindex e494470..bb4f6a9 100644[m
[1m--- "a/src\\graph\\client.py"[m
[1m+++ "b/.sandbox\\t0.7\\src\\graph\\client.py"[m
[36m@@ -1,15 +1,12 @@[m
[31m-"""Neo4j client and connection management (T0.3)."""[m
[32m+[m[32m"""Neo4j client module (T0.3)."""[m
 [m
 import os[m
 from pathlib import Path[m
 from dotenv import load_dotenv[m
[31m-from neo4j import Driver, GraphDatabase[m
[31m-[m
[32m+[m[32mfrom neo4j import GraphDatabase, Driver[m
 from src.log import get_logger[m
 [m
 ROOT = Path(__file__).resolve().parent.parent.parent[m
[31m-load_dotenv(ROOT / ".env")[m
[31m-[m
 logger = get_logger("client")[m
 [m
 [m
[36m@@ -18,24 +15,26 @@[m [mdef get_driver([m
     user: str | None = None,[m
     password: str | None = None,[m
 ) -> Driver:[m
[31m-    """Create and return a connected Neo4j driver instance.[m
[32m+[m[32m    """Return an authenticated Neo4j driver with verified connectivity.[m
 [m
[31m-    Reads NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD from the environment[m
[31m-    (loaded from .env via python-dotenv) if not explicitly provided.[m
[31m-    Calls verify_connectivity() before returning the driver.[m
[32m+[m[32m    Reads NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD from .env if not provided.[m
[32m+[m[32m    Calls verify_connectivity() before returning.[m
[32m+[m[32m    Closes driver if connectivity verification fails.[m
     """[m
     load_dotenv(ROOT / ".env")[m
[32m+[m
     uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")[m
     user = user or os.getenv("NEO4J_USER", "neo4j")[m
     password = password if password is not None else os.getenv("NEO4J_PASSWORD")[m
 [m
[31m-    auth = (user, password) if user and password is not None else None[m
[32m+[m[32m    auth = (user, password) if password is not None else None[m
[32m+[m
     driver = GraphDatabase.driver(uri, auth=auth)[m
     try:[m
         driver.verify_connectivity()[m
         logger.info("Connected to Neo4j at %s", uri)[m
[31m-    except Exception as exc:[m
[31m-        logger.error("Failed to connect to Neo4j at %s: %s", uri, exc)[m
[32m+[m[32m        return driver[m
[32m+[m[32m    except Exception as e:[m
         driver.close()[m
[32m+[m[32m        logger.error("Failed to connect to Neo4j at %s: %s", uri, e)[m
         raise[m
[31m-    return driver[m
