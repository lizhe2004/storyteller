# 单向流式语音合成HTTP

引用来源：https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-text-to-speech-http?lang=zh
基于 HTTP Chunked 协议的单向流式合成接口，一次性输入文本，流式返回音频，支持中、英、日、西等多语种及多种方言口音。

<span data-label="purple">POST</span> `https://openspeech.bytedance.com/api/v3/tts/unidirectional`


请求头


**X\-Api\-Key** `string` <span data-api-tag="require|4AobfA">必选</span>

API Key 可从 [控制台>API Key管理](https://console.volcengine.com/speech/new/setting/apikeys?projectName=default.) 获取



**X\-Api\-Resource\-Id** `string` <span data-api-tag="require|AMjHmz">必选</span>

请求的模型版本，可选值：


* `seed-tts-2.0`:豆包语音合成大模型2.0，支持使用[豆包语音合成模型2.0音色](https://docs.volcengine.com/docs/6561/1257544?lang=zh#%E8%B1%86%E5%8C%85%E8%AF%AD%E9%9F%B3%E5%90%88%E6%88%90%E6%A8%A1%E5%9E%8B2-0%E3%80%81s2s-o2-0%E3%80%81-s2s-%E5%85%A8%E5%8F%8C%E5%B7%A5-%E9%9F%B3%E8%89%B2%E5%88%97%E8%A1%A8)

* `seed-icl-2.0`:豆包声音复刻大模型2.0，支持使用声音复刻接口克隆的音色，具体音色详见[控制台>音色库](https://console.volcengine.com/speech/new/voices?projectName=default)



**X\-Api\-Request\-Id** `string` <span data-api-tag="require|urxyGl">必选</span>

标识客户端请求ID，uuid随机字符串



**X\-Control\-Require\-Usage\-Tokens\-Return** `string`

若设置为`*`，会返回计费的字符数




请求体


**req_params** `object` <span data-api-tag="require|CErO7k">必选</span>


**text** `string` <span data-api-tag="require|OeKzcE">必选</span>

输入待合成的文本



**model** `string`

指定模型版本，默认值为`seed-tts-2.0-standard`

<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>


<div data-tips="true" data-tips-type="tip">仅当<code>speaker</code>参数为复刻音色时需指定此参数，且指定后不支持使用语音指令<code>context_texts</code></div>




**speaker** `string` <span data-api-tag="require|8WfXlw">必选</span>

指定音色ID，具体的音色ID可从[控制台 > 音色库](https://console.volcengine.com/speech/new/voices?projectName=default)获取



**ssml** `string`

SSML标记文本，启用后将按SSML规则解析 `text`。SSML规则请参考：[SSML标记语言](https://docs.volcengine.com/docs/6561/1330194?lang=zh)

<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>



* <div data-tips="true" data-tips-type="tip">目前仅中英文音色支持ssml，音色详情请参考：<a href="https://docs.volcengine.com/docs/6561/1257544?lang=zh#%E8%B1%86%E5%8C%85%E8%AF%AD%E9%9F%B3%E5%90%88%E6%88%90%E6%A8%A1%E5%9E%8B2-0%E3%80%81s2s-o2-0%E3%80%81-s2s-%E5%85%A8%E5%8F%8C%E5%B7%A5-%E9%9F%B3%E8%89%B2%E5%88%97%E8%A1%A8">豆包语音合成模型2.0音色</a></div>


* <div data-tips="true" data-tips-type="tip">启用后需将<code>disable_markdown_filter</code>设置为<code>false</code>，否则此参数不生效</div>




**audio_params** `object` <span data-api-tag="require|61E198">必选</span>

音频参数


**format** `string`

指定音频格式，默认值为`mp3`，支持 `mp3` / `pcm` / `ogg_opus` / `wav`

<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>


<div data-tips="true" data-tips-type="tip">流式场景推荐使用<code>pcm</code>，不建议使用<code>wav</code></div>




**sample_rate** `int`

指定输出音频的采样率，单位为Hz，不同音频格式支持的采样率不同，详细如下：


* `wav`/`pcm`/`mp3`默认值为`24000`，取值范围为[`8000`,`16000`,`22050`，`24000`,`32000`,`44100`,`48000`]

* `ogg_opus`仅支持`48000`



**bit_rate** `int`

指定音频比特率，单位 bps，不同音频格式对比特率支持的情况不同，详细如下：


* `mp3`：默认为`64000` ，可选值[`64000`,`160000`]

* `ogg_opus`：可选值[`64000`,`160000`]

* `wav`/`pcm`：不支持指定比特率


<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>


<div data-tips="true" data-tips-type="tip">当设置<code>disable_default_bit_rate</code>为<code>true</code>后，可选值[<code>16000</code>,<code>32000</code>,<code>64000</code>,<code>160000</code>]</div>




**speech_rate** `int`

指定音频的语速，默认值为`0`，取值范围 [`-50`, `100`]。其中，取值`100`代表2.0倍速，`-50`代表0.5倍速



**loudness_rate** `int`

指定音频的音量，默认值为`0`，取值范围 [`-50`, `100`]。其中，取值`100`代表2.0倍音量，`-50`代表0.5倍音量



**enable_subtitle** `bool`

启用字幕服务，开启后将返回字级别的时间戳，默认值为`false`

<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>


<div data-tips="true" data-tips-type="tip">仅支持中文和英文语种</div>





**additions** `string`

配置自定义附加参数，须传入JSON序列化后的字符串


**max_length_to_filter_parenthesis** `int`

指定过滤括号内文本的长度，单位为字符，默认为0（即不过滤），推荐取值范围0~100

<div data-tips="true" data-tips-type="default" data-tips-is-title="true">说明</div>



* <div data-tips="true" data-tips-type="default">该参数用于过滤文本中括号内的注释、补充说明等无需朗读的内容</div>


* <div data-tips="true" data-tips-type="default">当括号内文本字符数超过设定值时，该括号的过滤功能将失效，括号内内容会被正常朗读。若存在较长的括号文本需要过滤，建议客户端在送入合成前自行完成前置过滤，以避免过滤失效及不必要的时延</div>




**silence_duration** `int`

配置文本末尾的静音时长，单位 ms，默认值为`0`，取值范围为[`0`,`30000`]



**disable_markdown_filter** `bool`

Markdown解析过滤参数，默认值为`false`


* `true`：启用后，系统会解析并去除Markdown语法，例如" **你好** "朗读为 "你好"

* `false`：停用后，系统会保留原始字符，例如 " **你好** " 朗读为 "星星你好星星"



**disable_emoji_filter** `bool`

Emoji解析过滤参数，默认值为`false`


* `true`：启用后，系统会解析并去除文本中的Emoji符号

* `false`：停用后，系统会保留文本中的Emoji符号



**latex_parser** `string`

启用Latex文本朗读能力功能。可取值：`v2`

<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>



* <div data-tips="true" data-tips-type="tip">该参数适用于教育场景，启用后，会增加一定的时延。</div>


* <div data-tips="true" data-tips-type="tip">启用该参数时，需同时将<code>disable_markdown_filter</code>设置为<code>true</code></div>




**explicit_language** `string`

指定朗读语种。开启后，仅朗读指定语种的文本，其他语种的内容会被跳过或合成失败，支持的语种如下：


* `zh-cn`：中文为主，支持中英混读

* `en`：英语

* `ja`：日语

* `es-mx`：墨西哥西语

* `id`：印度尼西亚语

* `pt-br`：巴西葡萄牙语

* `pt`：葡萄牙语

* `ko`：韩语

* `it`：意大利语

* `de`：德语

* `fr`：法语

* `th`：泰语

* `vi`：越南语

* `ru`：俄语

* `fil`：菲律宾语

* `ms`：马来语

* `ar`：阿拉伯语

* `pl`：波兰语

* `tr`：土耳其语

* `sv`：瑞典语

* `nl`: 荷兰语

* `no`: 挪威

* `uk`: 乌克兰语

* `fi`: 芬兰

* `da`: 丹麦

* `cs`: 捷克

* `hu`: 匈牙利

* `el`: 希腊

* `ro`: 罗马尼亚

* `hi`: 印度

* `es-es`: 西班牙西语


<div data-tips="true" data-tips-type="default" data-tips-is-title="true">说明</div>



* <div data-tips="true" data-tips-type="default">输入文本语种须与 <code>explicit_language</code> 指定的语种一致，不一致时合成效果不予保证</div>


* <div data-tips="true" data-tips-type="default"><a href="https://docs.volcengine.com/docs/DoubaoVoice/Tonelist-1?lang=zh#%E8%B1%86%E5%8C%85%E8%AF%AD%E9%9F%B3%E5%90%88%E6%88%90%E6%A8%A1%E5%9E%8B2-0%E3%80%81s2s-o2-0%E3%80%81-s2s-%E5%85%A8%E5%8F%8C%E5%B7%A5-%E9%9F%B3%E8%89%B2%E5%88%97%E8%A1%A8">豆包语音合成模型 2.0 音色列表</a>中，仅命名为zh_<em>xxx</em>_<em>xxxx</em>_uranus_bigtts的音色支持<code>nl</code>、<code>no</code>、<code>uk</code>、<code>fi</code>、<code>da</code>、<code>cs</code>、<code>hu</code>、<code>el</code>、<code>ro</code>、<code>hi</code>、<code>es-es</code>等语种</div>




**enable_auto_language_recognition**`bool`

开启自动多语种识别，默认为`false`，开启后，系统将根据首句文本自动识别语种，并使用对应语种进行朗读

<div data-tips="true" data-tips-type="default" data-tips-is-title="true">说明</div>



* <div data-tips="true" data-tips-type="default">指定语种的优先级高于自动多语种识别，当同时指定了<code>explicit_language</code>时，自动多语种识别不生效</div>


* <div data-tips="true" data-tips-type="default">支持的语种与 <code>explicit_language</code> 一致（<code>pt</code>与<code>es-es</code>除外）</div>


* <div data-tips="true" data-tips-type="default">自动识别语种时，葡萄牙语文本默认输出 <code>pt-br</code>（巴西口音），西班牙语文本默认输出 <code>es-mx</code>（墨西哥口音）。如需使用欧洲葡萄牙语<code>pt</code>或西班牙西班牙语<code>es-es</code>，须通过 <code>explicit_language</code> 参数显式指定</div>


* <div data-tips="true" data-tips-type="default">中英模型（中文、英文）与小语种模型（日、韩、法语、西语等小语种）相互独立，各自仅对对应语种合成效果最佳</div>




**explicit_dialect** `string`

指定方言


* `beijing`：北京话

* `dongbei`：东北话

* `henan`：河南话

* `shaanxi`：陕西话

* `shanghai`：上海话

* `sichuan`：四川话

* `tianjin`：天津话

* `yue`：粤语


<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>


<div data-tips="true" data-tips-type="tip">使用该参数时，<code>speaker</code>需要设置支持方言的音色。音色的详细情况请参见：<a href="https://docs.volcengine.com/docs/6561/1257544?lang=zh">音色列表</a></div>




**aigc_watermark** `bool`

启用AIGC生成标识，默认值：`false`。开启后，将在音频合成结尾添加节奏标识。



**aigc_metadata** `object`

在合成音频中添加meta水印，支持音频格式 `mp3` / `wav` / `ogg_opus`


**enable** `bool`

启用meta隐式水印，默认值：`false`



**content_producer** `string`

指定合成服务提供者的名称或编码



**produce_id** `string`

指定自定义的内容制作编号



**content_propagator** `string`

指定内容传播服务提供者的名称或编码



**propagate_id** `string`

指定自定义的内容传播编号




**post_process** `object`

后处理相关配置


**pitch** `int`

指定音调，默认值为0，默认不调整音调，取值范围：[\-12,12]

取值越大，音调越高（声音越尖锐、越明亮）；取值越小，音调越低（声音越低沉，越厚重）




**context_texts** `array`

配置语音指令

示例：

```Python
"context_texts":[ "你可以用特别特别痛心的语气说话吗?"]
```


<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>



* <div data-tips="true" data-tips-type="tip">仅<code>speaker</code>参数设置为<a href="https://docs.volcengine.com/docs/6561/1257544?lang=zh#%E8%B1%86%E5%8C%85%E8%AF%AD%E9%9F%B3%E5%90%88%E6%88%90%E6%A8%A1%E5%9E%8B2-0%E3%80%81s2s-o2-0%E3%80%81-s2s-%E5%85%A8%E5%8F%8C%E5%B7%A5-%E9%9F%B3%E8%89%B2%E5%88%97%E8%A1%A8">豆包语音合成模型2.0音色</a>时，支持使用语音指令</div>


* <div data-tips="true" data-tips-type="tip">该字段文字不参与计费</div>




**section_id** `string`

配置段落标识，可用于保持跨包语义

<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>


<div data-tips="true" data-tips-type="tip">该参数仅支持<a href="https://docs.volcengine.com/docs/6561/1257544?lang=zh#%E8%B1%86%E5%8C%85%E8%AF%AD%E9%9F%B3%E5%90%88%E6%88%90%E6%A8%A1%E5%9E%8B2-0%E3%80%81s2s-o2-0%E3%80%81-s2s-%E5%85%A8%E5%8F%8C%E5%B7%A5-%E9%9F%B3%E8%89%B2%E5%88%97%E8%A1%A8">豆包语音合成模型2.0音色</a>、豆包声音复刻大模型2.0音色</div>




**tone_fidelity** `bool`

开启还原模式，开启后模型将尽可能还原送入的训练的prompt音频音色和说话风格（情感、韵律、口音等）

默认值：`false`

<div data-tips="true" data-tips-type="tip" data-tips-is-title="true">说明</div>



* <div data-tips="true" data-tips-type="tip"><strong>仅适用于</strong>豆包声音复刻大模型2.0音色</div>


* <div data-tips="true" data-tips-type="tip"><strong>仅支持</strong>合成和训练音频同语种的文本<strong>，不支持</strong>跨语种合成<strong>，不支持</strong>双向流合成接口</div>




**pronunciation_dict**`object`

配置发音词典，修正指定文本的发音


**tone**`object`

配置发音规则数组，支持发音修正与文本转写两类规则


* 发音修正：`原词/(拼音音节)`，用于指定词汇的具体发音

* 文本转写：`原词/目标文本`，用于将原词替换为目标文本后再合成


 示例：

```Python
 "req_params": {
    "text": "我在北京说 omg",
    "speaker": "zh_female_vv_uranus_bigtts",
    "audio_params": {
      "format": "mp3",
      "sample_rate": 24000
    },
   "additions": "{\"pronunciation_dict\":{\"tone\":[\"北京/(bei3)(jing1)\",\"omg/oh my god\"]}}" 
  }
```


<div data-tips="true" data-tips-type="default" data-tips-is-title="true">说明</div>



* <div data-tips="true" data-tips-type="default"><code>tone </code>中每条规则采用<code> 原词/修正内容 </code>格式，以<code>/</code>分隔。服务端按文本从左到右进行贪心最长匹配，存在多个可匹配词条时，优先匹配更长的原词</div>


* <div data-tips="true" data-tips-type="default">最多支持配置 5000 个词条；每个原词长度不超过 9 个字符，不能为空、不能包含空格、不可重复</div>


* <div data-tips="true" data-tips-type="default">仅豆包语音合成大模型2.0、豆包语音复刻大模型2.0对应的中英文音色支持</div>


* <div data-tips="true" data-tips-type="default">命中发音字典规则的文本片段不支持 SSML 标签，同时使用时 SSML 标签将失效，建议二者择一</div>








响应


**X\-Tt\-Logid** `string`

服务端返回的 logid，用于在咨询或者反馈时定位问题



**code** `int`

状态码，返回`0`则表示语音合成成功，非`0`表示合成失败（具体含义见[错误码查询](https://docs.volcengine.com/docs/6561/2534853?lang=zh)）



**message** `string`

状态详情，返回`OK`则表示语音合成成功



**data** `string`

合成音频数据，base64编码



**sentence** `object`


**phonemes** `array`

音素相关时间戳



**text** `string`

合成音频文本



**words** `array`

字级别时间戳


**confidence** `float`

时间戳置信度，范围 0~1



**startTime** `float`

开始时间（秒）



**endTime** `float`

结束时间（秒）



**word** `string`

字





**usage** `object`

本次请求的资源消耗统计


**text_words** `int`

本次请求计费的文本字数（含标点）






