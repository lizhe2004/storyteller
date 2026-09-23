> ## Documentation Index
> Fetch the complete documentation index at: https://docs.bailian.console.aliyun.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Qwen-Audio-TTS音色列表

Qwen-Audio-TTS支持的系统音色如下表所示。除系统音色外，还提供通过声音复刻预先生成的基础音色，详情请参见[基础音色列表](/zh/model-studio/qwen-audio-tts-voice-list#ext-voices-title)。若需要更加个性化的音色，也可通过声音复刻功能免费定制专属音色，详情请参见[使用复刻的音色进行语音合成](/zh/model-studio/cosyvoice-clone-design-api)。

进行语音合成时：

- 每个模型（`model`）仅支持一组特定的音色（`voice`），不能将一个模型的音色与另一个模型混用。如果所填音色不在当前模型支持的音色列表中，服务将返回 `InvalidParameter` 错误（例如 `[cosyvoice:]Engine error [411]: TTS speak operation failed`）；此时请对照下方对应模型的音色列表，确认所填 voice 在当前 model 的支持范围内
- 待合成文本（`text`）必须在所选音色支持的语言范围内，否则可能出现发音错误或语音不自然

## qwen-audio-3.1-tts-flash系统音色列表 <span id="qwen-tts31-voices" />

以下音色适用于 `qwen-audio-3.1-tts-flash`。`voice` 值区分大小写。

### 多语种与方言音色 <span id="qwen-tts31-multilingual" />

以下四个音色均支持下列全部方言和语言。

- 方言：上海话、广东话、东北话、重庆话、陕西话、云南话、宁波话、甘肃话。
- 语言：日语、韩语、法语、德语、葡萄牙语、意大利语、越南语、印尼语。

<table className="table-wide" autofit="false" tablewidth="1000" style={{ overflowWrap: "anywhere" }}>
  <colgroup>
    <col style={{ width: "20%" }} />

    <col style={{ width: "25%" }} />

    <col style={{ width: "10%" }} />

    <col style={{ width: "45%" }} />
  </colgroup>

  <thead>
    <tr>
      <th style={{ verticalAlign: "top" }}>名称</th>
      <th style={{ verticalAlign: "top" }}>voice 参数</th>
      <th style={{ verticalAlign: "top" }}>性别</th>
      <th style={{ verticalAlign: "top" }}>试听</th>
    </tr>
  </thead>

  <tbody>
    <tr>
      <td style={{ verticalAlign: "top" }}>龙安欢\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longanhuan\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>

      <td style={{ verticalAlign: "top" }}>
        <div>
          <p style={{ marginTop: 0 }}>重庆话</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9ced.wav" />
        </div>

        <div>
          <p>宁波话</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9cec.wav" />
        </div>

        <div>
          <p>韩语</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9ce3.wav" />
        </div>

        <div>
          <p>印尼语</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9ce2.wav" />
        </div>
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙安灵心\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longanlingxin\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>

      <td style={{ verticalAlign: "top" }}>
        <div>
          <p style={{ marginTop: 0 }}>云南话</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9ce1.wav" />
        </div>

        <div>
          <p>陕西话</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9ce0.wav" />
        </div>

        <div>
          <p>上海话</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9ce7.wav" />
        </div>

        <div>
          <p>法语</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9ce6.wav" />
        </div>

        <div>
          <p>意大利语</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9ce5.wav" />
        </div>
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙安风悦\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longanfengyue\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>

      <td style={{ verticalAlign: "top" }}>
        <div>
          <p style={{ marginTop: 0 }}>东北话</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9ce4.wav" />
        </div>

        <div>
          <p>越南语</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9cfb.wav" />
        </div>

        <div>
          <p>日语</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9cfa.wav" />
        </div>
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>许南川</td>
      <td style={{ verticalAlign: "top" }}><code>xunanchuan\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>

      <td style={{ verticalAlign: "top" }}>
        <div>
          <p style={{ marginTop: 0 }}>甘肃话</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9cf9.wav" />
        </div>

        <div>
          <p>东北话</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9cf8.wav" />
        </div>

        <div>
          <p>法语</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9cff.wav" />
        </div>

        <div>
          <p>葡萄牙语</p>

          <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9cfe.wav" />
        </div>
      </td>
    </tr>
  </tbody>
</table>

### 精品中文音色 <span id="qwen-tts31-chinese" />

以下音色仅支持中文普通话。

<table className="table-wide" autofit="false" tablewidth="1200" style={{ overflowWrap: "anywhere" }}>
  <colgroup>
    <col style={{ width: "12%" }} />

    <col style={{ width: "18%" }} />

    <col style={{ width: "6%" }} />

    <col style={{ width: "14%" }} />

    <col style={{ width: "20%" }} />

    <col style={{ width: "30%" }} />
  </colgroup>

  <thead>
    <tr>
      <th style={{ verticalAlign: "top" }}>名称</th>
      <th style={{ verticalAlign: "top" }}>voice 参数</th>
      <th style={{ verticalAlign: "top" }}>性别</th>
      <th style={{ verticalAlign: "top" }}>声线特质</th>
      <th style={{ verticalAlign: "top" }}>适用场景</th>
      <th style={{ verticalAlign: "top" }}>试听</th>
    </tr>
  </thead>

  <tbody>
    <tr>
      <td style={{ verticalAlign: "top" }}>于小云</td>
      <td style={{ verticalAlign: "top" }}><code>yuxiaoyun\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>元气、亲切、自然</td>
      <td style={{ verticalAlign: "top" }}>广告营销、广播、客服助手、旁白</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9cfd.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>乔小娇</td>
      <td style={{ verticalAlign: "top" }}><code>qiaoxiaojiao\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>俏丽、可爱</td>
      <td style={{ verticalAlign: "top" }}>广告营销、客服助手、有声书</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9cfc.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>夏小晨</td>
      <td style={{ verticalAlign: "top" }}><code>xiaxiaochen\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>元气、明亮</td>
      <td style={{ verticalAlign: "top" }}>广告营销、有声书</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9cf2.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>安明远</td>
      <td style={{ verticalAlign: "top" }}><code>anmingyuan\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>清亮、自然</td>
      <td style={{ verticalAlign: "top" }}>广告营销、有声书、旁白</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9cf1.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>温怀清</td>
      <td style={{ verticalAlign: "top" }}><code>wenhuaiqing\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>清亮、柔和</td>
      <td style={{ verticalAlign: "top" }}>儿童故事、客服助手、广告营销、新闻播报</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9cf0.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>安小岚</td>
      <td style={{ verticalAlign: "top" }}><code>anxiaolan\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>清甜、纯净</td>
      <td style={{ verticalAlign: "top" }}>有声书、客服助手、旁白、新闻播报、广告营销</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9cf7.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>谢舒柔</td>
      <td style={{ verticalAlign: "top" }}><code>xieshurou\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>柔和、自然、知性</td>
      <td style={{ verticalAlign: "top" }}>有声书、客服助手、旁白</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9cf5.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>白清岚</td>
      <td style={{ verticalAlign: "top" }}><code>baiqinglan\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>明亮、清纯</td>
      <td style={{ verticalAlign: "top" }}>语音助手、客服助手</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c0b.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>许玉远</td>
      <td style={{ verticalAlign: "top" }}><code>xuyuyuan\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>知性、成熟、质感</td>
      <td style={{ verticalAlign: "top" }}>广告营销、新闻播报、旁白、客服助手、有声书</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c0a.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>安若柔</td>
      <td style={{ verticalAlign: "top" }}><code>anruorou\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>气声、知性</td>
      <td style={{ verticalAlign: "top" }}>旁白、语音助手</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c09.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>闻怀之</td>
      <td style={{ verticalAlign: "top" }}><code>wenhuaizhi\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>稳重、成熟</td>
      <td style={{ verticalAlign: "top" }}>有声书、新闻播报、广告营销、客服助手、旁白</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c08.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>萧行之</td>
      <td style={{ verticalAlign: "top" }}><code>xiaoxingzhi\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>端庄、贵气</td>
      <td style={{ verticalAlign: "top" }}>新闻播报、有声书、旁白、客服助手</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c0f.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>顾云舒</td>
      <td style={{ verticalAlign: "top" }}><code>guyunshu\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>成熟、稳重</td>
      <td style={{ verticalAlign: "top" }}>音乐电台、客服助手、有声书、旁白</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c0e.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>霍拙石</td>
      <td style={{ verticalAlign: "top" }}><code>huozhuoshi\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>清亮</td>
      <td style={{ verticalAlign: "top" }}>有声书、广告营销、旁白</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c0d.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>叶清禾</td>
      <td style={{ verticalAlign: "top" }}><code>yeqinghe\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>亲切、温柔</td>
      <td style={{ verticalAlign: "top" }}>有声书、广告营销、旁白、客服助手</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c0c.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>云欢欢</td>
      <td style={{ verticalAlign: "top" }}><code>yunhuanhuan\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>高亢、热情</td>
      <td style={{ verticalAlign: "top" }}>有声书、旁白、客服助手</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c03.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>徐小俏</td>
      <td style={{ verticalAlign: "top" }}><code>xuxiaoqiao\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>自然、俏皮</td>
      <td style={{ verticalAlign: "top" }}>有声书、旁白、客服助手</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c02.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>白安然</td>
      <td style={{ verticalAlign: "top" }}><code>baianran\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>低沉、浑厚、气声</td>
      <td style={{ verticalAlign: "top" }}>配音讲解、有声书、旁白</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c01.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>许言初</td>
      <td style={{ verticalAlign: "top" }}><code>xuyanchu\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>沉稳、磁性</td>
      <td style={{ verticalAlign: "top" }}>新闻播报、有声书</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c00.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>叶知晴</td>
      <td style={{ verticalAlign: "top" }}><code>yezhiqing\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>轻快、自然</td>
      <td style={{ verticalAlign: "top" }}>儿童故事、客服助手、语音助手</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c05.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>安迪</td>
      <td style={{ verticalAlign: "top" }}><code>andi\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>ABC口音</td>
      <td style={{ verticalAlign: "top" }}>语音助手</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c1b.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>安语晴</td>
      <td style={{ verticalAlign: "top" }}><code>anyuqing\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>甜妹</td>
      <td style={{ verticalAlign: "top" }}>语音助手、旁白、新闻播报</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c1a.wav" />
      </td>
    </tr>
  </tbody>
</table>

### 精品英文音色 <span id="qwen-tts31-english" />

以下音色仅支持英文。

<table className="table-wide" autofit="false" tablewidth="1000" style={{ overflowWrap: "anywhere" }}>
  <colgroup>
    <col style={{ width: "14%" }} />

    <col style={{ width: "22%" }} />

    <col style={{ width: "8%" }} />

    <col style={{ width: "16%" }} />

    <col style={{ width: "40%" }} />
  </colgroup>

  <thead>
    <tr>
      <th style={{ verticalAlign: "top" }}>名称</th>
      <th style={{ verticalAlign: "top" }}>voice 参数</th>
      <th style={{ verticalAlign: "top" }}>性别</th>
      <th style={{ verticalAlign: "top" }}>口音</th>
      <th style={{ verticalAlign: "top" }}>试听</th>
    </tr>
  </thead>

  <tbody>
    <tr>
      <td style={{ verticalAlign: "top" }}>Emily</td>
      <td style={{ verticalAlign: "top" }}><code>Emily\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>英式女声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c19.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>Luna</td>
      <td style={{ verticalAlign: "top" }}><code>Luna\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>英式女声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c18.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>Eric</td>
      <td style={{ verticalAlign: "top" }}><code>Eric\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>英式男声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c1f.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>Luca</td>
      <td style={{ verticalAlign: "top" }}><code>Luca\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>英式男声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c1e.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>Abby</td>
      <td style={{ verticalAlign: "top" }}><code>Abby\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>美式女声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c1d.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>Annie</td>
      <td style={{ verticalAlign: "top" }}><code>Annie\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>美式女声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c1c.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>Ava</td>
      <td style={{ verticalAlign: "top" }}><code>Ava\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>美式女声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c13.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>Beth</td>
      <td style={{ verticalAlign: "top" }}><code>Beth\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>美式女声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c12.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>Betty</td>
      <td style={{ verticalAlign: "top" }}><code>Betty\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>美式女声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c11.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>Cally</td>
      <td style={{ verticalAlign: "top" }}><code>Cally\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>美式女声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c10.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>Cindy</td>
      <td style={{ verticalAlign: "top" }}><code>Cindy\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>美式女声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c17.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>Donna</td>
      <td style={{ verticalAlign: "top" }}><code>Donna\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>美式女声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c16.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>Andy</td>
      <td style={{ verticalAlign: "top" }}><code>Andy\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>美式男声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c15.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>Brian</td>
      <td style={{ verticalAlign: "top" }}><code>Brian\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>美式男声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c14.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>David</td>
      <td style={{ verticalAlign: "top" }}><code>David\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>美式男声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c2b.wav" />
      </td>
    </tr>
  </tbody>
</table>

### 其他系统音色 <span id="qwen-tts31-additional" />

<table className="table-wide" autofit="false" tablewidth="1200" style={{ overflowWrap: "anywhere" }}>
  <colgroup>
    <col style={{ width: "12%" }} />

    <col style={{ width: "18%" }} />

    <col style={{ width: "6%" }} />

    <col style={{ width: "14%" }} />

    <col style={{ width: "20%" }} />

    <col style={{ width: "30%" }} />
  </colgroup>

  <thead>
    <tr>
      <th style={{ verticalAlign: "top" }}>名称</th>
      <th style={{ verticalAlign: "top" }}>voice 参数</th>
      <th style={{ verticalAlign: "top" }}>性别</th>
      <th style={{ verticalAlign: "top" }}>声线特质</th>
      <th style={{ verticalAlign: "top" }}>适用场景</th>
      <th style={{ verticalAlign: "top" }}>试听</th>
    </tr>
  </thead>

  <tbody>
    <tr>
      <td style={{ verticalAlign: "top" }}>龙安元妃\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longanyuanfei\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>高傲妃子音</td>
      <td style={{ verticalAlign: "top" }}>社交陪伴</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c2a.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙杰力豆\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longjielidou\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>天真男童音</td>
      <td style={{ verticalAlign: "top" }}>儿童陪伴</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c29.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙安灵希\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longanlingxi\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>可爱甜美音</td>
      <td style={{ verticalAlign: "top" }}>社交陪伴（精品中文）</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c2f.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙火火\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longhuohuo\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>顽皮少年音</td>
      <td style={{ verticalAlign: "top" }}>角色音</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c28.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙应桃\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longyingtao\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>温柔淡定女</td>
      <td style={{ verticalAlign: "top" }}>客服</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c2e.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙安雅\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longanya\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>高雅气质女</td>
      <td style={{ verticalAlign: "top" }}>社交陪伴</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c2d.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙婉\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longwan\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>细腻柔声女</td>
      <td style={{ verticalAlign: "top" }}>社交陪伴</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c2c.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙星\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longxing\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>温婉邻家女</td>
      <td style={{ verticalAlign: "top" }}>社交陪伴</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c23.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙华\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longhua\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>元气甜美女</td>
      <td style={{ verticalAlign: "top" }}>社交陪伴</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c22.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙寒\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longhan\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>温暖痴情男</td>
      <td style={{ verticalAlign: "top" }}>社交陪伴</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c21.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙安智\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longanzhi\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>睿智轻熟男</td>
      <td style={{ verticalAlign: "top" }}>社交陪伴</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c20.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙哲\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longzhe\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>呆板大暖男</td>
      <td style={{ verticalAlign: "top" }}>社交陪伴</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c27.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙安洋\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longanyang\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>阳光大男孩</td>
      <td style={{ verticalAlign: "top" }}>社交陪伴（标杆音色）</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c26.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>李白\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>libai\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>古代诗仙男</td>
      <td style={{ verticalAlign: "top" }}>诗词朗诵</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c25.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙铃\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longling\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>稚气呆板女</td>
      <td style={{ verticalAlign: "top" }}>童声</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c24.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙牛牛\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longniuniu\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>阳光男童声</td>
      <td style={{ verticalAlign: "top" }}>消费电子-儿童有声书</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c3b.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙闪闪\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longshanshan\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>戏剧化童声</td>
      <td style={{ verticalAlign: "top" }}>消费电子-儿童有声书</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c3a.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙泡泡\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longpaopao\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>飞天泡泡音</td>
      <td style={{ verticalAlign: "top" }}>消费电子-儿童陪伴</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c39.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>loongstella\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>loongstella\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>飒爽利落女</td>
      <td style={{ verticalAlign: "top" }}>新闻播报</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c38.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙媛\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longyuan\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>温暖治愈女</td>
      <td style={{ verticalAlign: "top" }}>有声书</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c3f.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙妙\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longmiao\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>抑扬顿挫女</td>
      <td style={{ verticalAlign: "top" }}>有声书</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c3e.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙三叔\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longsanshu\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>沉稳质感男</td>
      <td style={{ verticalAlign: "top" }}>有声书</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c3d.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙安莉\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longanli\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>利落从容女</td>
      <td style={{ verticalAlign: "top" }}>语音助手</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c3c.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙安温\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longanwen\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>优雅知性女</td>
      <td style={{ verticalAlign: "top" }}>语音助手</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c33.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙安朗\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longanlang\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>清爽利落男</td>
      <td style={{ verticalAlign: "top" }}>语音助手</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c32.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙小夏\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longxiaoxia\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>女</td>
      <td style={{ verticalAlign: "top" }}>沉稳权威女</td>
      <td style={{ verticalAlign: "top" }}>语音助手</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c31.wav" />
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>龙安冲\_v3.1</td>
      <td style={{ verticalAlign: "top" }}><code>longanchong\_v3.1</code></td>
      <td style={{ verticalAlign: "top" }}>男</td>
      <td style={{ verticalAlign: "top" }}>激情推销男</td>
      <td style={{ verticalAlign: "top" }}>直播带货</td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls src="https://g-adoc.alcasset.com/media/maas_docs/sfm-cn/common/audios/6a4b3c2d1e0f9c30.wav" />
      </td>
    </tr>
  </tbody>
</table>

## qwen-audio-3.0-tts-plus系统音色列表 <span id="f399ce27bcc8" />

<table style={{ display: "table", tableLayout: "fixed", width: "100%", overflowWrap: "anywhere" }}>
  <colgroup>
    <col style={{ width: "25%" }} />

    <col style={{ width: "35%" }} />

    <col style={{ width: "40%" }} />
  </colgroup>

  <thead>
    <tr>
      <th style={{ verticalAlign: "top" }}>
        <strong>适用场景</strong>
      </th>

      <th style={{ verticalAlign: "top" }}>
        <strong>音色信息</strong>
      </th>

      <th style={{ verticalAlign: "top" }}>
        <strong>音频试听（右键保存音频）</strong>
      </th>
    </tr>
  </thead>

  <tbody>
    <tr>
      <td rowSpan={2} style={{ verticalAlign: "top" }}>
        社交陪伴（旗舰音色）
      </td>

      <td style={{ verticalAlign: "top" }}>
        <strong>名称</strong>：龙安灵心

        <strong>voice参数</strong>：longanlingxin

        <strong>特质</strong>：知心温暖音

        <strong>年龄</strong>：25岁

        <strong>性别</strong>：女

        <strong>语言</strong>：中文（普通话）、英文
      </td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls>
          <source src="https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260706/deqsie/01_longanlingxin.wav" type="audio/x-wav" />
        </audio>
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>
        <strong>名称</strong>：龙安鲁风

        <strong>voice参数</strong>：longanlufeng

        <strong>特质</strong>：明亮开朗音

        <strong>年龄</strong>：25岁

        <strong>性别</strong>：男

        <strong>语言</strong>：中文（普通话）、英文
      </td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls>
          <source src="https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260706/tpgsdv/02_longanlufeng.wav" type="audio/x-wav" />
        </audio>
      </td>
    </tr>
  </tbody>
</table>

## qwen-audio-3.0-tts-flash系统音色列表 <span id="f399ce27bcc8flash" />

<table style={{ display: "table", tableLayout: "fixed", width: "100%", overflowWrap: "anywhere" }}>
  <colgroup>
    <col style={{ width: "25%" }} />

    <col style={{ width: "35%" }} />

    <col style={{ width: "40%" }} />
  </colgroup>

  <thead>
    <tr>
      <th style={{ verticalAlign: "top" }}>
        <strong>适用场景</strong>
      </th>

      <th style={{ verticalAlign: "top" }}>
        <strong>音色信息</strong>
      </th>

      <th style={{ verticalAlign: "top" }}>
        <strong>音频试听（右键保存音频）</strong>
      </th>
    </tr>
  </thead>

  <tbody>
    <tr>
      <td rowSpan={5} style={{ verticalAlign: "top" }}>
        社交陪伴（精品中文）
      </td>

      <td style={{ verticalAlign: "top" }}>
        <strong>名称</strong>：龙安风悦

        <strong>voice参数</strong>：longanfengyue

        <strong>特质</strong>：自然亲切音

        <strong>年龄</strong>：30岁

        <strong>性别</strong>：女

        <strong>语言</strong>：中文（普通话）、英文
      </td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls>
          <source src="https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260706/djxajf/03_longanfengyue.wav" type="audio/x-wav" />
        </audio>
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>
        <strong>名称</strong>：龙安元妃

        <strong>voice参数</strong>：longanyuanfei

        <strong>特质</strong>：高傲妃子音

        <strong>年龄</strong>：30岁

        <strong>性别</strong>：女

        <strong>语言</strong>：中文（普通话）、英文
      </td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls>
          <source src="https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260706/lnyaxv/04_longanyuanfei.wav" type="audio/x-wav" />
        </audio>
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>
        <strong>名称</strong>：龙安灵希

        <strong>voice参数</strong>：longanlingxi

        <strong>特质</strong>：可爱甜美音

        <strong>年龄</strong>：25岁

        <strong>性别</strong>：女

        <strong>语言</strong>：中文（普通话）、英文
      </td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls>
          <source src="https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260706/pfkypj/05_longanlingxi.wav" type="audio/x-wav" />
        </audio>
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>
        <strong>名称</strong>：龙安小昕

        <strong>voice参数</strong>：longanxiaoxin

        <strong>特质</strong>：亲切活泼音

        <strong>年龄</strong>：22岁

        <strong>性别</strong>：女

        <strong>语言</strong>：中文（普通话）、英文
      </td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls>
          <source src="https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260706/msjxqk/07_longanxiaoxin.wav" type="audio/x-wav" />
        </audio>
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>
        <strong>名称</strong>：龙安欢

        <strong>voice参数</strong>：longanhuan\_v3.6

        <strong>年龄</strong>：25岁

        <strong>性别</strong>：女

        <strong>语言</strong>：中文（普通话）、英文
      </td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls>
          <source src="https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260706/glwaer/09_longanhuan.wav" type="audio/x-wav" />
        </audio>
      </td>
    </tr>

    <tr>
      <td rowSpan={2} style={{ verticalAlign: "top" }}>
        儿童陪伴/智能玩具（精品儿童）
      </td>

      <td style={{ verticalAlign: "top" }}>
        <strong>名称</strong>：龙杰力豆

        <strong>voice参数</strong>：longjielidou\_v3.6

        <strong>特质</strong>：天真男童

        <strong>年龄</strong>：5岁

        <strong>性别</strong>：男

        <strong>语言</strong>：中文（普通话）、英文
      </td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls>
          <source src="https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260706/wirytn/08_longjielidou.wav" type="audio/x-wav" />
        </audio>
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>
        <strong>名称</strong>：龙泡泡

        <strong>voice参数</strong>：longpaopao\_v3.6

        <strong>特质</strong>：软糯可爱音

        <strong>年龄</strong>：5岁

        <strong>性别</strong>：女

        <strong>语言</strong>：中文（普通话）、英文
      </td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls>
          <source src="https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260706/nrgkjo/13_longpaopao.wav" type="audio/x-wav" />
        </audio>
      </td>
    </tr>

    <tr>
      <td rowSpan={2} style={{ verticalAlign: "top" }}>
        角色音/游戏（精品中文）
      </td>

      <td style={{ verticalAlign: "top" }}>
        <strong>名称</strong>：龙火火

        <strong>voice参数</strong>：longhuohuo\_v3.6

        <strong>特质</strong>：顽皮少年音

        <strong>年龄</strong>：8岁

        <strong>性别</strong>：男

        <strong>语言</strong>：中文（普通话）、英文
      </td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls>
          <source src="https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260706/efdgqh/11_longhuohuo.wav" type="audio/x-wav" />
        </audio>
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>
        <strong>名称</strong>：龙川叔

        <strong>voice参数</strong>：longchuanshu\_v3.6

        <strong>特质</strong>：川普大叔音

        <strong>年龄</strong>：40岁

        <strong>性别</strong>：男

        <strong>语言</strong>：中文（普通话）、英文
      </td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls>
          <source src="https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260706/makxfd/12_longchuanshu.wav" type="audio/x-wav" />
        </audio>
      </td>
    </tr>

    <tr>
      <td rowSpan={3} style={{ verticalAlign: "top" }}>
        社交陪伴/语音助手（精品英文）
      </td>

      <td style={{ verticalAlign: "top" }}>
        <strong>名称</strong>：loongmary

        <strong>voice参数</strong>：loongmary

        <strong>特质</strong>：温暖英音

        <strong>年龄</strong>：20岁

        <strong>性别</strong>：女

        <strong>语言</strong>：英文
      </td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls>
          <source src="https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260706/wpitzn/01_loongmary.wav" type="audio/x-wav" />
        </audio>
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>
        <strong>名称</strong>：loongeva

        <strong>voice参数</strong>：loongeva\_v3.6

        <strong>特质</strong>：高智美音

        <strong>年龄</strong>：28岁

        <strong>性别</strong>：女

        <strong>语言</strong>：英文
      </td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls>
          <source src="https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260706/xajwqw/02_loongeva.wav" type="audio/x-wav" />
        </audio>
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>
        <strong>名称</strong>：loongJohn

        <strong>voice参数</strong>：loongjohn

        <strong>特质</strong>：沉稳亲切美音

        <strong>年龄</strong>：28岁

        <strong>性别</strong>：男

        <strong>语言</strong>：英文
      </td>

      <td style={{ verticalAlign: "top" }}>
        <audio controls>
          <source src="https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260706/pwxpto/03_loongjohn_1.wav" type="audio/x-wav" />
        </audio>
      </td>
    </tr>
  </tbody>
</table>

## 基础音色列表 <span id="ext-voices-title" />

<Note>
  建议优先使用系统音色，以获得更稳定的语音合成效果。如需定制音色，可通过[声音复刻](/zh/model-studio/voice-cloning-user-guide)或[声音设计](/zh/model-studio/voice-design-user-guide)创建专属音色。基础音色提供更多选择，使用前建议试听并评估其是否符合业务需求。
</Note>

除上述系统音色外，`qwen-audio-3.0-tts-plus`和`qwen-audio-3.0-tts-flash`各自还提供500余个通过声音复刻生成的基础音色，调用方式与系统音色一致。基础音色命名格式为`qwen-audio-3.0-tts-{plus|flash}-{音色后缀}`，两个模型同一后缀对应同一套试听音频。完整音色列表请下载下方Excel查看：

- `qwen-audio-3.0-tts-plus`基础音色列表（Excel）：[qwen-audio-3.0-tts-plus基础音色.xlsx](https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260723/ydwqqz/qwen-audio-3.0-tts-plus%E5%9F%BA%E7%A1%80%E9%9F%B3%E8%89%B2.xlsx)
- `qwen-audio-3.0-tts-flash`基础音色列表（Excel）：[qwen-audio-3.0-tts-flash基础音色.xlsx](https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260723/thosjr/qwen-audio-3.0-tts-flash%E5%9F%BA%E7%A1%80%E9%9F%B3%E8%89%B2.xlsx)
- 基础音色试听音频包（plus和flash共用）：[基础音色试听音频包.zip](https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260720/tuuuqo/%E5%9F%BA%E7%A1%80%E9%9F%B3%E8%89%B2%E8%AF%95%E5%90%AC%E9%9F%B3%E9%A2%91%E5%8C%85.zip)

<strong>试听步骤</strong>：

1. 下载Excel和试听音频包，将音频包解压到本地。
2. 在Excel中找到“预览音频文件名”列，获取音频文件名。
3. 在解压目录中找到对应文件，使用播放器打开试听。
