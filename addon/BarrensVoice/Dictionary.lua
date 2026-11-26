-- The slang dictionary ("WTS" is said as "продам"): the addon keeps it - the default here and the
-- player's edits as a layer over it - and the companion applies it (it reads the default from this
-- file and gets the layer over the strip, Core.lua ns.SendDictionary). One entry per line,
-- "key=replacement"; case and ё/е do not matter; "#" starts a comment. A key is a word, a phrase
-- ("мертвые копи"), or a stem ending in "*" ("дамагер*" also takes "дамагера"; a "*" in the
-- replacement gets the ending). A replacement may mark stress with "+" before the vowel ("дам+агер");
-- the companion turns that into what each voice understands. An empty replacement drops the word. A
-- line starting with "~" is a regular expression (Python, case-insensitive, split at the last "=").
local _, ns = ...

local D = {}
ns.Dictionary = D

D.DEFAULT = [[
# слово=как читать; ударение: + перед гласной (дам+агер)
# фразы: мертвые копи=мёртвые к+опи; склонения: дамагер*=дам+агер* (окончание переносится)
# регулярки (Python, применяет лаунчер): ~(\d+)к\b=\g<1>000
# «т.е.», «т. е.» = «то есть»; слитно со словом («т.е.я пас») — с пробелом (\040: пробел в конце замены срезается), а слово
# остаётся вне замены, и словарь берёт его дальше («т.е.рл» — «то есть эр-эл»).
# Стоит до правил чисел: их замена в метке, и «т.е.60лвл» склеилось бы
~\bт\.\s*е\.(?=[а-яёa-z\d+])=то есть\040
~\bт\.\s*е\b\.?=то есть
~\b(\d+)\s*(?:лвл|lvl|ур|уровень)\b=<\1> уровень
# «<3» — сердечко, смайлик: пауза, как у «:)». Только в конце строки, где его и ставят, вместе с «<333», разбитым «</3» и несколькими подряд. В середине строки «<3» — число: «кд <3 сек», «<3к голды». Стоит до правил чисел.
~(?:\s*<\/?3+)+(?=[\s.!?)]*$)=.
# «+-» (аддон говорит «+» словом): плюс-минус; «+-5» = «плюс-минус 5» (до правил чисел: «+-5%»)
~\bплюс\s*-(?=\s|$)=плюс-минус
~\bплюс(\s+)-(?=\d)=плюс-минус\1
# год после «с», «в», «после»: «играю с 2005г» = «с две тысячи пятого года», «в 2007г» = «в две тысячи седьмом году» (а «продам за 2000г» — золото,
# и «обошлось в 2000г» тоже: круглая сотня слитно с «г» после «в» — цена, а «в 2000 г» через пробел — год)
~\b(с|со|после)\s+((?:19|20)\d\d)\s*г\b=\1 \2 года
~\b(в|во)\s+((?:19|20)\d\d)(?:\s+|(?<!00))г\b=\1 \2 году
# и конец диапазона лет (только сразу после года): «с 2005г по 2010г» = «… по две тысячи десятый год», «с 2005г до 2010г» = «… до две тысячи десятого года»
~(?<=(?:19|20)\d\d по |года по |ода\W по )((?:19|20)\d\d)\s*г\b=\1 год
~(?<=(?:19|20)\d\d до |года до |ода\W до )((?:19|20)\d\d)\s*г\b=\1 года
# цена слитно: «2г50с», «5з20с» = «два золотых пятьдесят серебра»
~\b(\d+)\s*(?:з|g|г)(\d+)\s*(?:с|s)\b=\1 [золотой|золотых|золотых] \2 [серебро|серебра|серебра]
# и без «с»: «2г50» = «два золотых пятьдесят» (серебро — одна-две цифры)
~\b(\d+)\s*(?:з|g|г)(\d{1,2})\b=\1 [золотой|золотых|золотых] \2
~\b(\d+)\s*(?:з|g)\b=\1 [золотой|золотых|золотых]
# «г», приклеенное к числу, — тоже золото: «100г» = «сто золотых»
~\b(\d+)г\b=\1 [золотой|золотых|золотых]
~\b(\d+)\s*(?:голд|г\+олд)\w*\b=\1 [золотой|золотых|золотых]
~\b(\d+)\s*шт\b\.?=\1 [штука|штуки|штук]
~\b(\d+)\s*%=\1 [процент|процента|процентов]
# «см» строчными (и «См») после числа — сантиметры, без числа не трогаем («см. выше», «го в см»); «СМ» заглавными — подземелье Монастырь Алого ордена
~\b(\d+)\s*(?-i:см|См)\b=\1 [сантиметр|сантиметра|сантиметров]
# арена «2х2», «5x5», «3v3», «2 х 2» = «два на два», «пять на пять», «три на три» (слитно или через пробелы: «уровень 40 х2» — «сорок икс два»)
~\b(\d+)(?:[хxv]|\s+[хxv]\s+)(\d+)\b=\1 на \2
# «х2 опыт», «x3» = «икс два», «икс три»
~\b[хx](\d{1,2})\b=икс \1
# здоровье — количество, а не порядковое: «100 хп» = «сто здоровья», «10к хп» = «десять тысяч здоровья» (тысячи — правилом «к» ниже)
~\b(\d+кк?)\s*(?:хп|hp|здоровь\w*)\b=\1 здоровья
# «10 к хп» — тоже тысячи («хп» к этому времени склонилось после «к»: «здоровью»), а «+100 к здоровью» — бонус к здоровью
~(?<!плюс )\b(\d+\s+кк?)\s*(?:хп|hp|здоровь\w*)\b=\1 здоровья
~\b(\d+)\s*(?:хп|hp|здоровье)\b=\1 [здоровье|здоровья|здоровья]
# «кд 30 с», «каст 2 с» — секунды (а не серебро в конце фразы)
~\b(кулд\+?аун\w*|кд|cd|каст\w*|откат\w*)\s+(\d+)(?:\s*сек\b|(?:с|s)\b|\s+(?:с|s)\b(?=\s*$|\s*[-–—,.!?;)]))=\1 \2 [секунда|секунды|секунд]
~(?<!через )\b(\d+)(?:с|s)\b(?!\s*(?:кд|cd|кулд\+?аун))=\1 [серебро|серебра|серебра]
# через пробел «с» после числа — серебро в конце фразы и перед ценой: «продам за 5 с», «5 с за штуку», «5 с 20 м»;
# иначе это предлог: «нас 5 с хилом», «2 с половиной часа»
~(?<!через )\b(\d+)\s+(?:с|s)\b(?=\s*$|\s*[-–—,.!?;)]|\s+(?:за|(?:и|или)(?!\s+без\b)|кажд(?:ый|ая|ое|ую|ого)|шт|штук\w*|стак\w*|\d+\s*(?:м|m|медн\w*))\b)=\1 [серебро|серебра|серебра]
# «5 с кд» — секунды, хотя «кд» уже склонилось после «с» («с кулдауном»)
~\b(\d+)\s+(?:с|s)\s+кулд\+?аун(?:ом)?\b=\1 [секунда|секунды|секунд] кулд+аун
# секунды — только где понятно, что это время: «через 5с», «5с кд» (в остальных местах «5с» — серебро);
# «кд» к этому времени уже «кулдаун» (слова заменяются раньше регулярок), поэтому ждём оба
~(?<=через )(\d+)\s*(?:с|s|сек)\b(?!\s+(?:половиной|лишним|хвостиком))=\1 [секунду|секунды|секунд]
~\b(\d+)\s*(?:с|s|сек)\b(?=\s*(?:кд|cd|кулд\+?аун)\b)=\1 [секунда|секунды|секунд]
# число и роль: 2дд = «2 дамагера»; в [ ] три формы: для 1, для 2-4, для 5 и больше; <\1> — порядковое: «60 лвл» = «шестидесятый уровень»
~\b(\d+)\s*(?:дд|дам\+агер)\b=\1 [дам+агер|дам+агера|дам+агеров]
~\b(\d+)\s*(?:рдд|дальний дам\+агер)\b=\1 [дальний дам+агер|дальних дам+агера|дальних дам+агеров]
~\b(\d+)\s*(?:мдд|ближний дам\+агер)\b=\1 [ближний дам+агер|ближних дам+агера|ближних дам+агеров]
~\b(\d+)\s*(?:хилл?|х\+ил)\b=\1 [х+ил|х+ила|х+илов]
~\b(\d+)\s*(?:танк|т\+анк)\b=\1 [т+анк|т+анка|т+анков]
~\bдд(\d{1,2})\b=дам+агер, уровень \1
~\bрдд(\d{1,2})\b=дальний дам+агер, уровень \1
~\bмдд(\d{1,2})\b=ближний дам+агер, уровень \1
~\bхилл?(\d{1,2})\b=х+ил, уровень \1
~\bтанк(\d{1,2})\b=т+анк, уровень \1
~\bварр?(\d{1,2})\b=воин, уровень \1
~\bприст(\d{1,2})\b=жрец, уровень \1
~\bшам(\d{1,2})\b=шам+ан, уровень \1
~\bхант(\d{1,2})\b=охотник, уровень \1
~\bмаг(\d{1,2})\b=маг, уровень \1
~\bрог[аи]?(\d{1,2})\b=разбойник, уровень \1
~\bлок(\d{1,2})\b=чернокнижник, уровень \1
~\bпал(\d{1,2})\b=паладин, уровень \1
~\bдру(?:ль|ид)?(\d{1,2})\b=друид, уровень \1
# т1, t2 — тир комплекта брони (0–21: в ритейле до 21): «тэ один» (иначе «тодин»); только отдельным словом, не «5т1». Число словами: цифру
# числа согласовали бы со словом после — «т2 сет» стало бы «тэ второй сет», «т1 шапка» — «тэ одна шапка»
~\b[тt]0\b=тэ ноль
~\b[тt]1\b=тэ один
~\b[тt]2\b=тэ два
~\b[тt]3\b=тэ три
~\b[тt]4\b=тэ четыре
~\b[тt]5\b=тэ пять
~\b[тt]6\b=тэ шесть
~\b[тt]7\b=тэ семь
~\b[тt]8\b=тэ восемь
~\b[тt]9\b=тэ девять
~\b[тt]10\b=тэ десять
~\b[тt]11\b=тэ одиннадцать
~\b[тt]12\b=тэ двенадцать
~\b[тt]13\b=тэ тринадцать
~\b[тt]14\b=тэ четырнадцать
~\b[тt]15\b=тэ пятнадцать
~\b[тt]16\b=тэ шестнадцать
~\b[тt]17\b=тэ семнадцать
~\b[тt]18\b=тэ восемнадцать
~\b[тt]19\b=тэ девятнадцать
~\b[тt]20\b=тэ двадцать
~\b[тt]21\b=тэ двадцать один
~(\d+)\s*кк\b=\g<1>000000
# «кк» без числа — «окей» (регуляркой, после миллионов: словом оно съедало «за 2 кк» = «за два окей»)
~\bкк\b=окей
# «к» с пробелом после числа — тысячи, только если дальше количество, «до», «или», тире или ничего: «2 к голды», «5 к дпс», «от 5 к до 10 к», «продам за 3 к».
# Иначе это предлог: «обмен 2 к 1», а после «плюс» — всегда («+5 к урону» — бонус). «голды» к этому времени склонилось после «к» («г+олдам»)
~(\d+)\s+к\s+г\+?олд\w*=\g<1>000 г+олды
~(?<!плюс )\b(\d+)\s+к\b(?=\s*$|\s*[-–—,.!?;)]|\s+(?:здоровь[ея]|золот[оа]|золотых|серебр[оа]|урона?|дамага?|ман[аы]|опыта?|эксп[аы]|брон[яи]|рейтинга?|рейта?|чест[ьи]|хонора?|реп(?:[аы]|утация)?|дпс|dps|дэ пэ \+?эс|хпс|hps|гс|gs|хилл?а|до|или|и|за|в|на)\b)=\g<1>000
# и после цены («за», «от», «до» перед числом), если дальше не число: «за 5 к отдам», «продам за 5 к срочно» (а «за 1 к 1» — обмен; «по 5 к силе» — бонус каждому)
~\b(за|от|до)\s+(\d+)\s+к\b(?!\s*\d|\s+(?:сил[еу]|ловкост[иь]|урону|броне|здоровью|мане|духу|интеллекту|выносливост[иь]|рейтингу|вечеру|утру|ночи|обеду|нам|вам|ним|нему|ней|мне|тебе|себе)\b)=\1 \g<2>000
# и перед словом торга: «нужно 5 к срочно», «5 к отдам» (целым словом: «3 к дам+агеру» — предлог)
~(?<!плюс )\b(\d+)\s+к\b(?=\s+(?:срочно|отдам|продам|куплю|возьму|дам|плачу|заплачу|есть|нужно|надо|пожалуйста|торг|сверху)(?![\w+]))=\g<1>000
# «репутации» — и родительный, и дательный: тысячи только для одной-двух цифр («20 к репутации»), «500 к репутации» — бонус к ней
~(?<!плюс )\b(\d{1,2})\s+к(?=\s+репутации\b)=\g<1>000
~(\d+)к\b=\g<1>000
# «ЛИ» — только заглавными: «ли» — частица («есть ли танк?»), а словарь и регулярки не различают регистр без (?-i:…)
~(?-i:\bЛИ\b)=Лабиринты Иглошкурых
WTS=продам
# «рмт» (RMT, торговля за реальные деньги) — по буквам
рмт=Эр Эм Тэ
RMT=Эр Эм Тэ
# «в душе» — душа́: «в душе не знаю», «добрый в душе» (иначе читается как душ)
в душе=в душ+е
WTB=куплю
WTT=обменяю
LFG=ищу группу
LFM=ищем ещё
LF=ищу
LF1M=нужен ещё один
LF2M=нужны ещё двое
LF3M=нужны ещё трое
ty=спасибо
thx=спасибо
спс=спасибо
пасиб=спасибо
pls=пожалуйста
plz=пожалуйста
плз=пожалуйста
пж=пожалуйста
пжл=пожалуйста
нзч=не за что
хз=не знаю
пздц=пиздец
мб=может быть
кст=кстати
кста=кстати
бтв=кстати
# «скрафтить» — скр+афтить, все формы
скрафт*=скр+афт*
# «вендор» (торговец) — в+ендор, все формы
вендор*=в+ендор*
# «форевер» (WoW Forever) — фор+евер, все формы
форевер*=фор+евер*
# «бургер» — б+ургер, все формы («бургеры», «бургеров»)
бургер*=б+ургер*
# «Гномреган» — гномрег+ан, все формы («в Гномрегане»)
гномреган*=гномрег+ан*
# «хуево» — «хуёво», все формы («хуевый», «хуёвина», «до хуев»): в словаре «ё» (yo_safe.txt) мата нет
хуев*=хуёв*
спек=сп+ек
оч=очень
прив=привет
пок=пока
ок=окей
ok=окей
gg=гуд гейм
гг=гуд гейм
afk=отошёл
афк=отошёл
brb=сейчас вернусь
discord=диск+орд
дискорд*=диск+орд*
oom=нет маны
оом=нет маны
кд=кулд+аун
cd=кулд+аун
хп=здоровье
дд=дам+агер
рдд=дальний дам+агер
мдд=ближний дам+агер
дамагер*=дам+агер*
хилер*=х+илер*
пл=лидер группы
лс=личку
тп=телепорт
нид=нужно
инст=инстанс
хил=х+ил
хилл=х+ил
хилы=х+илы
танк=т+анк
танч*=т+анч*
чилов*=чил+ов*
# чекнуть (проверить): ч+екну, ч+екни, ч+екнул
чекн*=ч+екн*
# «чекать»: RUAccent ставит «чек+ать» («чекаю», «чекай» он ставит верно); не «чека*» — это и «чекан»
чекать=ч+екать
пиши=пиш+и
губа=губ+а
тикет*=т+икет*
хелло=хелл+оу
менеджмент*=м+енеджмент*
манаменеджмент*=манам+енеджмент*
кастер=к+астер
мили=м+или
вар=воин
варр=воин
прист=жрец
шам=шам+ан
хант=охотник
хардкор*=хардк+ор*
друль=друид
дру=друид
лок=чернокнижник
варлок=чернокнижник
твинк=тв+инк
нуб=н+уб
лфг=ищу группу
лфм=ищем людей
LFR=ищу рейд
LF4M=нужны ещё четверо
пати=п+ати
ресет=рес+ет
аттюн=атт+юн
ролл=р+олл
грид=жадность
AH=аукцион
аук=аукц+ион
аука=аукци+она
ауке=аукци+оне
ауку=аукци+ону
ауком=аукци+оном
ауки=аукци+оны
ауков=аукци+онов
голд=г+олд
голды=г+олды
маунт=м+аунт
лут=л+ут
BoE=привязка при надевании
BoP=привязка при поднятии
агро=+агро
агрятся=+агрятся
агрится=+агрится
агрить=+агрить
агрит=+агрит
агрил=+агрил
агрила=+агрила
агрили=+агрили
агрю=+агрю
аггро=+агро
пул=п+ул
кача=к+ача
# качаться — прокачиваться (кач+ается), не раскачиваться: формы по одной
качается=кач+ается
качаются=кач+аются
качаться=кач+аться
качаюсь=кач+аюсь
качаешься=кач+аешься
качаемся=кач+аемся
качаетесь=кач+аетесь
качался=кач+ался
качалась=кач+алась
качались=кач+ались
качайся=кач+айся
качаясь=кач+аясь
качайтесь=кач+айтесь
качалось=кач+алось
пулл=п+ул
пуллить=п+уллить
вайп=в+айп
кайт=к+айт
кайтить=к+айтить
сап=с+ап
сайленс=с+айленс
# «баф», «бафы», «бафает», «бафнул», «дебафы» (и с двумя «ф») — ударение на «а», все формы; «Бафомет» — на «е»
бафомет*=бафом+ет*
дебаф*=деб+аф*
ребаф*=реб+аф*
баф*=б+аф*
аое=а о +е
AoE=а о +е
хот=х+от
дот=д+от
рес=р+ес
ресс=р+ес
дс=диск+орд
инк=инк+ам
inc=инк+ам
адд=+адд
моб=м+об
мобы=м+обы
треш=тр+эш
трэш=тр+эш
респ=р+есп
дпс=дэ пэ +эс
dps=дэ пэ +эс
фарм=ф+арм
гринд=гр+инд
ганк=г+анк
лос=линия видимости
LoS=линия видимости
лвл=уровень
lvl=уровень
# формы «лвл»: окончание у «уровня» другое, поэтому каждая отдельно
лвла=уровня
лвлу=уровню
лвлом=уровнем
лвле=уровне
лвлы=уровни
лвлов=уровней
лвлам=уровням
лвлами=уровнями
лвлах=уровнях
лол=л+ол
lol=л+ол
ппц=писец
омг=о боже
omg=о боже
имхо=+имхо
imho=+имхо
вп=хорошо сыграно
wp=хорошо сыграно
гз=поздравляю
gz=поздравляю
grats=поздравляю
грац=поздравляю
gl=удачи
гл=удачи
ГИ=гильдия
hf=приятной игры
np=не за что
sry=извини
сори=с+ори
btw=кстати
omw=уже иду
wtf=что за чёрт
имба=имб+а
импрувед=импр+увед
лк=эл к+а
х3=икс три
бк=бэ к+а
нерф=н+ерф
ОП=Огненная пр+опасть
RFC=Огненная пр+опасть
огненная пропасть=Огненная пр+опасть
огненную пропасть=Огненная пр+опасть
огненной пропасти=Огненная пр+опасть
огненной пропастью=Огненная пр+опасть
WC=Пещеры стенаний
ПС=Пещеры стенаний
дедмайнс=Мёртвые копи
КТК=Крепость Тёмного Клыка
SFK=Крепость Тёмного Клыка
стокады=Тюрьма Штормграда
перекрест*=перекр+ёст*
понож*=п+онож*
че=чё
ниче=ничё
# «темп» — с твёрдым «т», по формам (основа «темп*» задела бы «температуру»)
темп=тэмп
темпа=тэмпа
темпу=тэмпу
темпом=тэмпом
темпе=тэмпе
темпы=тэмпы
темпов=тэмпов
темпам=тэмпам
темпами=тэмпами
темпах=тэмпах
чето=чёто
пикабу=пикаб+у
подгород*=П+одгород*
серег*=серёг*
сереж*=серёж*
долбаеб*=долбаёб*
долбоеб*=долбоёб*
ПВП=пэвэп+э
ПВЕ=пэ-вэ-й+е
МСК=эм-эс-к+а
др=дэ-+эр
ружье=ружьё
берет=берёт
берете=берёте
нюдес*=н+юдес*
нюдс*=н+юдс*
кв=квест
тг=телегр+ам
доведет=довед+ёт
доведешь=довед+ёшь
доведем=довед+ём
доведете=довед+ёте
ага=аг+а
PvP=пэвэп+э
PvE=пэ-вэ-й+е
~\b(?-i:НП)\b=Непроглядная пучина
BFD=Непроглядная пучина
гномер=Гномрег+ан
суманем=суман+ём
суманешь=суман+ёшь
суманет=суман+ёт
суманете=суман+ёте
суману=суман+у
суманут=суман+ут
сумануть=суман+уть
суманул=суман+ул
суманула=суман+ула
суманули=суман+ули
# димоны (демоны) — только множественное: «Димон» без него — имя, с ударением на «о»
димоны=д+имоны
димонов=д+имонов
димонам=д+имонам
димонами=д+имонами
# стакаться (складываться в стопку), не «стакан»: формы по одной
стакается=ст+акается
стакаются=ст+акаются
стакаться=ст+акаться
стакалось=ст+акалось
стакались=ст+акались
стакалась=ст+акалась
стакался=ст+акался
стакает=ст+акает
стакают=ст+акают
стакать=ст+акать
стакаем=ст+акаем
стакал=ст+акал
стакай=ст+акай
стакала=ст+акала
стакали=ст+акали
стакаю=ст+акаю
стакаешь=ст+акаешь
стакаете=ст+акаете
застакается=заст+акается
застакаются=заст+акаются
застакалось=заст+акалось
застакался=заст+акался
застакалась=заст+акалась
застакались=заст+акались
RFK=Лабиринты Иглошкурых
РФК=Лабиринты Иглошкурых
RFD=Курганы Иглошкурых
РФД=Курганы Иглошкурых
~\b(?-i:СМ)\b=Монастырь Алого ордена
SM=Монастырь Алого ордена
ульда=Ульдам+ан
ЗФ=Зул'Ф+аррак
ZF=Зул'Ф+аррак
# «Глуб+ины»: без ударения RUAccent читает «го брд» как «глубин+ы»
БРД=Глуб+ины Чёрной горы
BRD=Глуб+ины Чёрной горы
ЛБРС=Нижняя часть Пика Чёрной горы
LBRS=Нижняя часть Пика Чёрной горы
УБРС=Верхняя часть Пика Чёрной горы
UBRS=Верхняя часть Пика Чёрной горы
страт=Стратх+ольм
strat=Стратх+ольм
шоло=Некросит+ет
некро=Некросит+ет
MC=Огненные недра
# Ониксия — он+иксия во всех формах
оникси*=он+икси*
БВЛ=Логово Крыла Тьмы
BWL=Логово Крыла Тьмы
ЗГ=Зул'Гур+уб
ZG=Зул'Гур+уб
АК20=Руины Ан'Кираджа
АК40=Храм Ан'Кираджа
AQ=Ан'Кир+адж
накс=Наксрам+ас
БГ=поле боя
BG=поле боя
АВ=Альтеракская долина
AV=Альтеракская долина
АБ=Низина Арати
AB=Низина Арати
ВСГ=Ущелье Песни Войны
WSG=Ущелье Песни Войны
]] ..
-- The «=!» entries (a replacement kept as written) go in a part of their own: a launcher before them (beta 19 and
-- older) reads the first part only (its regex takes one long string) and would read «!» aloud («после! скачек»);
-- without them it reads these words as before. The addon and newer launchers join the parts (dictionary.default_text).
[[
# «нп» строчными (и «Нп» в начале фразы) — «без проблем», «НП» заглавными — подземелье Непроглядная пучина
~\b(?-i:нп|Нп)\b=!без проблем
# «скачки» — ск+ачки: скачивание («скачки патча»), как и конные скачки. Всплески — скачк+и: «скачки фпс», «скачки по фпс», «скачки в пинге», «скачки дпс», «скачки урона», «скачки и лаги».
# «=!» — замену не склонять: «после скачки клиента» остаётся «скачки», а не «скачек»
~\bскачки(?=\s+(?:(?:по|в)\s+)?(?:фпс|fps|пинга?|пингу|пинге|лага?|лагу|лагов|кадров|кадрам|фреймрейта|задержки|дпс|dps|дэ пэ \+?эс|урона|урону|хп|hp|здоровь[яею])\b|\s+и\s+лаг)=!скачк+и
~\bскачки\b=!ск+ачки
# глобал — общий канал (гл+обал): формы по одной, не «глобальный»; «=!» — как написано (склонение делало «из гл+обалы»)
глобал=!гл+обал
глобала=!гл+обала
глобалу=!гл+обалу
глобале=!гл+обале
глобалом=!гл+обалом
глобалы=!гл+обалы
глобалов=!гл+обалов
глобалам=!гл+обалам
глобалами=!гл+обалами
глобалах=!гл+обалах
# сам аддон и сайты аддонов, как их пишут в чате латиницей; «=!» — не склонять (склонялось одно первое слово: «с К+ёрсом Ф+ордж»)
barrens voice=!Б+эрренс В+ойс
barrensvoice=!Б+эрренс В+ойс
curse forge=!К+ёрс Ф+ордж
curseforge=!К+ёрс Ф+ордж
wago.io=!В+аго
wago=!В+аго
# «РЛ» — по буквам, «эр-эл»: рейд-лидер или руины Лордерона, по словам вокруг не угадать («у РЛ спроси», «РЛ кинул
# инвайт», «из РЛа выйди»). Окончание — как написано («РЛу» — «эр-элу»), после числа — в лад с ним; «=!» — не склонять
# («к РЛ» — «к эр-эл», а не «к эр-элу»). Ударение — перед гласной. Ключи — как в 0.4.0: правка игрока встаёт на место
# своего правила. Окончания — раньше числа: «2 рла», «5 РЛ-ам» — окончание игрока
~\bрл-?(а|у|ом|ы|ов|ам|ами|е)\b=!эр-+эл\1
~\bрл-?ах\b=!эр-+элах
~\b(\d+)\s*рл\b=!\1 [эр-+эл|эр-+эла|эр-+элов]
~\bрл\b=!эр-+эл
# «БР» — по буквам (боевое воскрешение, «брр», «бр» — брат); после числа — в лад с ним: «есть 2 бр» — «два бэ-эра»;
# «2 БР-а», «бр-р» — как написаны. «бэ+эр» без дефиса: «бэ-+эра» склонение чисел принимает за «эру» («вторая»)
~\b(\d+)\s*бр\b(?!-[а-яё])=!\1 [бэ+эр|бэ+эра|бэ+эров]
~\bбр\b(?!-[а-яё])=!бэ+эр
# дарова, здарова, даров, дарово, здаров, здарово, дароу, здароу — приветствие (не «здорово»: RUAccent различает сам); «=!» — не склонять: «о, дарова!» склонялось в «о, дар+овой!»
дарова=!дар+ова
здарова=!здар+ова
даров=!дар+ов
дарово=!дар+ово
здаров=!здар+ов
здарово=!здар+ово
дароу=!дар+оу
здароу=!здар+оу
# новичек — так пишут «новичок»: «новичёк»; «=!» — не склонять (как «дарова» после «о»)
новичек=!новичёк
# ёмаё — междометие: «=!» — не склонять («о емае» не «о ёмае»)
емае=!ёма+ё
# морока — RUAccent путает с «м+орок» (мгла): «вечно морока то танка нет» — «м+орока». Каждая форма отдельно («морок*»
# взял бы и «морок»); «=!» — не склонять: «без мороки» иначе «без мор+оков»
морока=!мор+ока
мороки=!мор+оки
мороке=!мор+оке
мороку=!мор+оку
морокой=!мор+окой
# Степи — зона: в чате это почти всегда она («го Степи», «в Степи», «Пылающие степи»), а RUAccent без «в» и после
# «в» читает «степ+и» (место в одной степи). «=!» — не склонять: «из степи», «по степи» тоже «Ст+епи» (основное
# ударение и для этих форм). Цена — настоящая степь в местном падеже («в широкой степи») тоже «Ст+епи»
степи=!Ст+епи
# Плеть (нежить): «армия Плети», «некрополь Плети» — RUAccent часто «плет+и»; «плети» как кнуты — то же ударение,
# а «плети» от «плести» в чате редко
плети=!Пл+ети
# Топи (Пылевые, Чёрные…): «идём в топи» — RUAccent «в топ+и»; только после «в»: «топи» само — ещё и «топить»
в топи=!в Т+опи
# другие названия из таблиц игры, которые RUAccent (он читает строку строчными) читает не так; только полным
# названием («леса» сами по себе — и лес+а, и л+еса); «=!» — их пишут уже в нужном падеже («на Келебраса Проклятого»
# склонялось в «на Келебрасу»)
леса ночной песни=!Лес+а Ночн+ой П+есни
глубины черной горы=!Глуб+ины Чёрной горы
келебрас проклятый=!Келебрас Пр+оклятый
келебраса проклятого=!Келебраса Пр+оклятого
акульи воды=!Акульи в+оды
земли хаккари=!З+емли Хаккари
земли иглогривых=!З+емли Иглогривых
земли ящеров=!З+емли Ящеров
горы штормграда=!Г+оры Штормграда
острова эха=!Остров+а Эха
острова черного копья=!Остров+а Чёрного Копь+я
пронзающего копья=!Пронзающего Копь+я
поля великанов=!Пол+я Великанов
# «слезы» RUAccent оставляет без «ё»; по формам: «слез» отдельно — ещё и глагол («слез с коня»)
грот слез=!Грот Слёз
грота слез=!Грота Слёз
гроте слез=!Гроте Слёз
гроту слез=!Гроту Слёз
гротом слез=!Гротом Слёз
озеро слез=!Озеро Слёз
озера слез=!Озера Слёз
озере слез=!Озере Слёз
озеру слез=!Озеру Слёз
озером слез=!Озером Слёз
слезы далсона=!Слёзы Далсона
слез далсона=!Слёз Далсона
# Буру Ненасытный — босс; одним словом: так его и пишут («го на Буру»), а «бура», «бур» в чате редки
буру=!Б+уру
# оня, онька — рейд Ониксии: «Ониксия», как и говорят («идём на Ониксию»); «они» — местоимение, не трогать.
# оне — «на оне»: без записи RUAccent читает как старое местоимение «он+е»
# «=!» — не склонять: «о, оня!» склонялось в «о, Он+иксии!»
оня=!Он+иксия
онька=!Он+иксия
оню=!Он+иксию
оньку=!Он+иксию
оне=!Он+иксии
# «хуева туча» — х+уева т+уча (много, от «хуй»), не «хуёва» (основа «хуев*» выше); «хуевато» — хуев+ато. «=!» — не склонять: склонение делало «из х+уёвых т+уч»
хуева туча=!х+уева т+уча
хуеву тучу=!х+уеву т+учу
хуевой тучи=!х+уевой т+учи
хуевой тучей=!х+уевой т+учей
хуевой туче=!х+уевой т+уче
хуевато=!хуев+ато
# «о димонах»: склонение делало «о д+имонахе»
димонах=!д+имонах
# Ростов-на-Дону: каждая форма как написана, «=!» — не склонять (склонение коверкает составное название)
ростов-на-дону=!Ростов-на-Дон+у
ростова-на-дону=!Ростова-на-Дон+у
ростове-на-дону=!Ростове-на-Дон+у
ростову-на-дону=!Ростову-на-Дон+у
ростовом-на-дону=!Ростовом-на-Дон+у
# «рога» — разбойник (сленг), р+ога во всех формах: так пишут чаще, чем о рогах. «=!» — форма как написана
~\bрог(а|и|у|е|ой|ам|ами|ах|ов)\b=!р+ог\1
]]


-- Sorting (D.Text): Russian keys first, then Latin, then digits and other symbols, regexes (~)
-- last; within a group alphabetically (case and ё/е ignored). Comments travel with the entry below
-- them; the comment block at the top stays the header.
local function SortKey(entry)
    if entry:sub(1, 1) == "~" then return 4, entry end
    local key = D.Norm(entry:match("^(.-)%s*=") or entry)
    local first = key:byte(1) or 0
    if first >= 0xC0 then return 1, key end
    if key:match("^%a") then return 2, key end
    return 3, key
end

--- Lower case for ASCII and Russian letters, with ё as е (UTF-8; Lua's lower() knows ASCII only).
--- Byte lengths are kept, so a normalised word and the original line up byte for byte.
function D.Norm(s)
    -- ASCII by hand rather than s:lower(): byte for byte, whatever the client's lower() does with
    -- UTF-8 (on the ruRU Forever client lower() handles Cyrillic correctly too).
    s = s:gsub("[A-Z]", function(c) return string.char(c:byte() + 32) end)
    s = s:gsub("\208([\144-\159])", function(c) return "\208" .. string.char(c:byte() + 32) end)
    s = s:gsub("\208([\160-\175])", function(c) return "\209" .. string.char(c:byte() - 32) end)
    s = s:gsub("\208\129", "\208\181"):gsub("\209\145", "\208\181")
    return s
end

local WORD = "[%w\128-\255]+"

local function Words(s)
    local out = {}
    for w in s:gmatch(WORD) do out[#out + 1] = D.Norm(w) end
    return out
end

--- After the dictionary changed: tell the program (over the strip, Core.lua) and keep the player's
--- layer in the saved variables for a program that reads them (the game not running or the layer
--- not sent yet). The dictionary is applied by the program, not here: it reads the default straight
--- from this file, so a new default works without a /reload.
function D.Rebuild()
    if ns.DictionaryChanged then ns.DictionaryChanged() end
    ns.db.dictionaryUser = (D.SentLayer())
end

-- Layers. The default (D.DEFAULT) lives in the addon; the player's dictionary is the default with
-- their edits on top, and only the edits are saved - db.dictionaryEdits = {
--     lines = { [key] = "block" },  -- entries changed or added, with the comments above them
--     removed = { [key] = true },   -- default entries deleted
--     header = "...",               -- the comment block at the top, when changed
-- }
-- An entry left as it is is not stored, so a changed default reaches it by itself; an edited one
-- wins over the default; a deleted one stays deleted; a new default entry simply appears. A newer
-- default from GitHub (DictionaryOnline.lua, below) takes the place of this one.

--- The identity of a dictionary line: its normalised words ("*" for a stem), or for a regex its
--- pattern - all before the last "=" - so a changed reading is still the same entry. nil for a
--- line that is no entry.
function D.KeyOf(line)
    local trimmed = line:match("^%s*(.-)%s*$")
    if trimmed:sub(1, 1) == "#" then return nil end      -- a comment, "=" or not (as the companion's key_of)
    if trimmed:sub(1, 1) == "~" then
        return ((trimmed:match("^(.*)=") or trimmed):match("^(.-)%s*$"))
    end
    local key = trimmed:match("^(.-)%s*=")
    if not key or key == "" then return nil end
    local star = key:sub(-1) == "*"
    local words = Words(star and key:sub(1, -2) or key)
    if #words == 0 then return nil end
    return table.concat(words, " ") .. (star and "*" or "")
end

--- `text` cut into its header (the comments at the top) and its entries by key, each with the
--- comments above it: { header = "...", blocks = { [key] = "comments\nline" }, lines = { [key] = "line" } }.
local function Blocks(text)
    local header, blocks, lines, pending, top = {}, {}, {}, {}, true
    for line in ((text or "") .. "\n"):gmatch("(.-)\r?\n") do
        local trimmed = line:match("^%s*(.-)%s*$")
        if trimmed:sub(1, 1) == "#" then
            if top then header[#header + 1] = trimmed else pending[#pending + 1] = trimmed end
        elseif trimmed ~= "" then
            top = false
            local key = D.KeyOf(trimmed) or ("?" .. trimmed)   -- not an entry: kept as it is
            pending[#pending + 1] = trimmed
            local block = table.concat(pending, "\n")
            blocks[key] = blocks[key] and (blocks[key] .. "\n" .. block) or block
            lines[key] = lines[key] and (lines[key] .. "\n" .. trimmed) or trimmed
            pending = {}
        end
    end
    if #pending > 0 then blocks["#"] = table.concat(pending, "\n") end   -- comments after the last entry
    return { header = table.concat(header, "\n"), blocks = blocks, lines = lines }
end

local default, merged
local function Default()
    default = default or Blocks(D.DEFAULT)
    return default
end

--- Forget the cached default and merged text (after D.DEFAULT changes: a new layer, a test).
function D.Invalidate()
    default, merged = nil, nil
end

local function Edits()
    local e = ns.db.dictionaryEdits
    if not e then
        e = { lines = {}, removed = {} }
        ns.db.dictionaryEdits = e
    end
    e.lines, e.removed = e.lines or {}, e.removed or {}
    return e
end

--- The player's dictionary: the default with their edits, sorted block by block (the comments
--- above an entry go with it; the header stays on top).
function D.Text()
    if merged then return merged end
    local def, e = Default(), Edits()
    local items = {}
    local function Add(block)
        local group, key = SortKey(block:match("([^\n]*)$"))
        items[#items + 1] = { block = block, group = group, key = key }
    end
    for key, block in pairs(def.blocks) do
        if key ~= "#" and not e.removed[key] and not e.lines[key] then Add(block) end
    end
    for key, block in pairs(e.lines) do
        if key ~= "#" then Add(block) end
    end
    table.sort(items, function(x, y)
        if x.group ~= y.group then return x.group < y.group end
        if x.key ~= y.key then return x.key < y.key end
        return x.block < y.block
    end)
    local out = {}
    local header = e.header or def.header
    if header ~= "" then out[#out + 1] = header end
    for _, item in ipairs(items) do out[#out + 1] = item.block end
    local tail = e.lines["#"] or (not e.removed["#"] and def.blocks["#"])
    if tail then out[#out + 1] = tail end
    merged = table.concat(out, "\n") .. "\n"
    return merged
end

--- The edits that make the default into `text`: an entry is unchanged when its block, comments
--- included, is the default's.
local function Diff(text)
    local def, mine = Default(), Blocks(text)
    local e = { lines = {}, removed = {} }
    if mine.header ~= def.header then e.header = mine.header end
    for key, block in pairs(mine.blocks) do
        if def.blocks[key] ~= block then e.lines[key] = block end
    end
    for key in pairs(def.blocks) do
        if not mine.blocks[key] then e.removed[key] = true end
    end
    return e
end

--- The game's edit box keeps a typed or pasted "|" as "||" (its escape: "|c", "|T", "|H" are markup there, as
--- in the chat; the client's own login form takes "||" back to "|", AccountLogin.lua, forever and live), while
--- the dictionary has the plain "|" of a regex's "или" and of forms "[а|б|в]". The window puts its text in
--- escaped and takes it back unescaped: every "|" in the box is then "||", typed or not.
function D.Escaped(text) return (text:gsub("|", "||")) end
function D.Unescaped(text) return (text:gsub("||", "|")) end

--- The dictionary window's text, saved as edits of the default.
function D.SetText(text)
    ns.db.dictionaryEdits = Diff(text)
    merged = nil
    D.Rebuild()
end

--- The player's layer as the program takes it, one line each, sorted (a stable checksum): their
--- changed and added entry lines, and "!<default line>" for each default entry they deleted - the
--- line, not its key, so the program finds the key itself; "-" for none.
function D.UserLayer()
    local e, def = Edits(), Default()
    local out = {}
    for key, block in pairs(e.lines) do
        if key ~= "#" then
            for line in (block .. "\n"):gmatch("(.-)\n") do
                if line ~= "" and line:sub(1, 1) ~= "#" then out[#out + 1] = line end
            end
        end
    end
    for key in pairs(e.removed) do
        for line in ((def.lines[key] or "") .. "\n"):gmatch("(.-)\n") do
            if line ~= "" then out[#out + 1] = "!" .. line end
        end
    end
    table.sort(out)
    return #out > 0 and table.concat(out, "\n") or "-"
end

-- The longest line of the layer the program gets: the strip carries the layer in parts of this many
-- bytes (Core.lua ns.SendDictionary), and a longer line cut would be another rule, or a broken one.
D.MAX_LINE = 480

--- The player's layer as the program gets it, over the strip and from the saved variables alike (so a
--- rule never works in one session and not in the next): D.UserLayer without its lines longer than
--- D.MAX_LINE; "-" for none. Those lines are the second result.
function D.SentLayer()
    local kept, long = {}, {}
    local layer = D.UserLayer()
    if layer ~= "-" then
        for line in (layer .. "\n"):gmatch("(.-)\n") do
            if #line > D.MAX_LINE then long[#long + 1] = line else kept[#kept + 1] = line end
        end
    end
    return #kept > 0 and table.concat(kept, "\n") or "-", long
end

--- Back to the default: no edits.
function D.Reset()
    ns.db.dictionaryEdits = { lines = {}, removed = {} }
    merged = nil
    D.Rebuild()
end

-- Default entries whose key (a regex pattern) changed: old key -> new key, or a list of new keys when
-- the entry became several. Whoever edited or deleted the old entry keeps their choice: no new default
-- entry appears beside it. Written with long strings ([[...]]): the program reads this table from the
-- file too (bv/dictionary.py addon_renamed). dictionary.json carries a list as one string, the keys
-- joined by "\n" (tools/dictionary_json.py), so its "renamed" stays a map of strings older programs read.
D.RENAMED = {
    -- «бр» was a word: two rules now, with a number («2 бр» — «два бэ-эра») and without; who changed or deleted the
    -- word gets neither
    [ [[бр]] ] = { [[~\b(\d+)\s*бр\b(?!-[а-яё])]], [[~\bбр\b(?!-[а-яё])]] },
    -- "через N с" was seconds before «с половиной» too: «через 2 с половиной часа» is no seconds
    [ [[~(?<=через )(\d+)\s*(?:с|s|сек)\b]] ] = [[~(?<=через )(\d+)\s*(?:с|s|сек)\b(?!\s+(?:половиной|лишним|хвостиком))]],
    -- "N с" was one rule: glued it is silver, spaced only at the end of a phrase («нас 5 с хилом» is the preposition)
    [ [[~(?<!через )\b(\d+)\s*(?:с|s)\b(?!\s*(?:кд|cd|кулд\+?аун))]] ] = {
        [[~(?<!через )\b(\d+)(?:с|s)\b(?!\s*(?:кд|cd|кулд\+?аун))]],
        [[~(?<!через )\b(\d+)\s+(?:с|s)\b(?=\s*$|\s*[-–—,.!?;)]|\s+(?:за|(?:и|или)(?!\s+без\b)|кажд(?:ый|ая|ое|ую|ого)|шт|штук\w*|стак\w*|\d+\s*(?:м|m|медн\w*))\b)]],
    },
    -- "кк" was a word: a word goes before the regexes and took "2 кк" (millions) for "окей"
    [ [[кк]] ] = [[~\bкк\b]],
    -- "нп" was a word, any case: «нп» in lower case is «без проблем» now, the dungeon «НП» in capitals only
    [ [[нп]] ] = [[~\b(?-i:НП)\b]],
    -- "см" was a word, any case: «см» in lower case after a number is centimetres now, the dungeon «СМ» in capitals only
    [ [[см]] ] = [[~\b(?-i:СМ)\b]],
    -- a year after «в» is no round hundred glued to «г»: «обошлось в 2000г» is gold, «в 2000 г» a year
    [ [[~\b(в|во)\s+((?:19|20)\d\d)\s*г\b]] ] = [[~\b(в|во)\s+((?:19|20)\d\d)(?:\s+|(?<!00))г\b]],
    -- a spaced «к» before «репутации» is thousands for one or two digits only: a rule of its own; prices and
    -- trade words after it are new rules beside it
    [ [[~(?<!плюс )\b(\d+)\s+к\b(?=\s*$|\s*[-–—,.!?;)]|\s+(?:здоровь[ея]|золот[оа]|золотых|серебр[оа]|урона?|дамага?|ман[аы]|опыта?|эксп[аы]|брон[яи]|рейтинга?|рейта?|чест[ьи]|хонора?|реп(?:[аы]|утаци[яи])?|дпс|dps|дэ пэ \+?эс|хпс|hps|гс|gs|хилл?а|до|или|и|за|в|на)\b)]] ] = {
        [[~(?<!плюс )\b(\d+)\s+к\b(?=\s*$|\s*[-–—,.!?;)]|\s+(?:здоровь[ея]|золот[оа]|золотых|серебр[оа]|урона?|дамага?|ман[аы]|опыта?|эксп[аы]|брон[яи]|рейтинга?|рейта?|чест[ьи]|хонора?|реп(?:[аы]|утация)?|дпс|dps|дэ пэ \+?эс|хпс|hps|гс|gs|хилл?а|до|или|и|за|в|на)\b)]],
        [[~\b(за|от|до)\s+(\d+)\s+к\b(?!\s*\d|\s+(?:сил[еу]|ловкост[иь]|урону|броне|здоровью|мане|духу|интеллекту|выносливост[иь]|рейтингу|вечеру|утру|ночи|обеду|нам|вам|ним|нему|ней|мне|тебе|себе)\b)]],
        [[~(?<!плюс )\b(\d+)\s+к\b(?=\s+(?:срочно|отдам|продам|куплю|возьму|дам|плачу|заплачу|есть|нужно|надо|пожалуйста|торг|сверху)(?![\w+]))]],
        [[~(?<!плюс )\b(\d{1,2})\s+к(?=\s+репутации\b)]],
    },
    -- "N к" was one rule: glued, spaced before gold, spaced before an amount are rules of their own
    [ [[~(\d+)\s*к\b]] ] = {
        [[~(\d+)\s+к\s+г\+?олд\w*]],
        [[~(?<!плюс )\b(\d+)\s+к\b(?=\s*$|\s*[-–—,.!?;)]|\s+(?:здоровь[ея]|золот[оа]|золотых|серебр[оа]|урона?|дамага?|ман[аы]|опыта?|эксп[аы]|брон[яи]|рейтинга?|рейта?|чест[ьи]|хонора?|реп(?:[аы]|утация)?|дпс|dps|дэ пэ \+?эс|хпс|hps|гс|gs|хилл?а|до|или|и|за|в|на)\b)]],
        [[~\b(за|от|до)\s+(\d+)\s+к\b(?!\s*\d|\s+(?:сил[еу]|ловкост[иь]|урону|броне|здоровью|мане|духу|интеллекту|выносливост[иь]|рейтингу|вечеру|утру|ночи|обеду|нам|вам|ним|нему|ней|мне|тебе|себе)\b)]],
        [[~(?<!плюс )\b(\d+)\s+к\b(?=\s+(?:срочно|отдам|продам|куплю|возьму|дам|плачу|заплачу|есть|нужно|надо|пожалуйста|торг|сверху)(?![\w+]))]],
        [[~(?<!плюс )\b(\d{1,2})\s+к(?=\s+репутации\b)]],
        [[~(\d+)к\b]],
    },
}

--- The new keys of a renamed default entry (a value of D.RENAMED): a key, a list of keys, or keys
--- joined by "\n" (as dictionary.json carries a list).
function D.RenamedTo(new)
    if type(new) == "table" then return new end
    local keys = {}
    for key in (tostring(new) .. "\n"):gmatch("(.-)\n") do
        if key ~= "" then keys[#keys + 1] = key end
    end
    return keys
end

-- Which default this is: the time of the last commit that changed this file (tools/release.py sets it in a
-- release; 0 here, in the repository). The program fetches a fresher default from GitHub (the dictionary
-- online, bv/online_dictionary.py) and writes it into DictionaryOnline.lua, loaded before this file: the
-- newer of the two is the default, so a later addon update with a newer dictionary is not hidden by an
-- older download.
D.REVISION = 0
local online = BarrensVoiceDictionaryOnline
if type(online) == "table" and type(online.text) == "string" and (tonumber(online.revision) or 0) > D.REVISION then
    D.DEFAULT, D.REVISION = online.text, tonumber(online.revision)
    for old, new in pairs(type(online.renamed) == "table" and online.renamed or {}) do D.RENAMED[old] = new end
end

--- Once per load: the edits' tables in place, and renamed default entries (D.RENAMED) carrying
--- over the player's choice.
function D.Migrate(db)
    db.dictionaryEdits = db.dictionaryEdits or { lines = {}, removed = {} }
    local e = db.dictionaryEdits
    e.lines, e.removed = e.lines or {}, e.removed or {}
    -- 0.4.0 beta 17 and before saved the edit box's text as it was: a typed "|" as "||" (D.Escaped), and a regex
    -- "(а||б)" matches the empty string, so every chat line came out garbled. Once, taken back to "|" (no rule has a
    -- real "||"), a regex's key with it: its pattern is the key.
    if not db.dictionaryPipes then
        local lines = {}
        for key, block in pairs(e.lines) do
            block = D.Unescaped(block)
            local last = block:match("([^\n]*)$")
            local k = key == "#" and "#" or (D.KeyOf(last) or ("?" .. last))
            lines[k] = lines[k] and (lines[k] .. "\n" .. block) or block   -- two that became one: both kept, as Blocks does
        end
        e.lines = lines
        if e.header then e.header = D.Unescaped(e.header) end
        db.dictionaryPipes = true
    end
    for old, new in pairs(D.RENAMED) do
        if e.removed[old] or e.lines[old] then
            for _, key in ipairs(D.RenamedTo(new)) do e.removed[key] = true end
        end
        e.removed[old] = nil
    end
    merged = nil
end

