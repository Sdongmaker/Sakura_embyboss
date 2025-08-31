"""
简洁的播放器链接生成器
通过播放器类型直接生成对应链接
"""
from urllib.parse import quote

def generate_player_link(player_type: str, username: str, password: str) -> str:
    """
    生成指定播放器的导入链接
    
    Args:
        player_type: 播放器类型 ("senplayer", "hills")
        username: 用户名
        password: 密码
    
    Returns:
        对应播放器的导入链接
    """
    if not username or password == '空':
        return ''
    
    # 服务器配置
    server_config = {
        'scheme': 'http',
        'host': '38.246.112.104', 
        'port': '8095',
        'name': '起点影视',
        'note': '高清影视服务器'
    }
    
    if player_type.lower() == "senplayer":
        # SenPlayer链接生成
        base_url = f"{server_config['scheme']}://{server_config['host']}:{server_config['port']}"
        
        params = [
            f"type=emby",
            f"name={quote(server_config['name'])}",
            f"note={quote(server_config['note'])}",
            f"address={base_url}",
            f"username={quote(str(username))}",
            f"password={quote(str(password))}",
            f"address1name={quote('备用线路1')}",
            f"address1=http://backup1.example.com:8095"
        ]
        
        return f"senplayer://importserver?{'&'.join(params)}"
    
    elif player_type.lower() == "hills":
        # Hills链接生成
        params = [
            f"type=emby",
            f"scheme={server_config['scheme']}",
            f"host={server_config['host']}",
            f"port={server_config['port']}",
            f"username={quote(str(username))}",
            f"password={quote(str(password))}"
        ]
        
        hills_url = f"hills://import?{'&'.join(params)}"
        return f"https://gocy.pages.dev/#{hills_url}"
    
    else:
        return ''