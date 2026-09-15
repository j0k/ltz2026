# -*- coding: utf-8 -*-
"""Шпаргалка scikit-learn «Choosing the right estimator» для /tz/ml-map.html с оценкой для задачи 04.

Схема повторяет официальную шпаргалку scikit-learn (https://scikit-learn.org/stable/machine_learning_map.html, BSD):
координаты — в системе 1280×703. У каждого алгоритма — используется ли на стенде и перспективность для контроля качества
DXA с обоснованием; у решений — наш ответ. Оценки на 16.09.2026: scikit-learn в стенде не используется, анализ на правилах
numpy (профили яркости, порог Отсу, медианные фильтры, геометрия оси). Меняется реализация — правьте used и ours здесь.

Данные организатора, на которые опираются оценки: 100 исследований, 499 DICOM, 252 уникальных снимка; у позвоночника
нарушение в 32 из 99 исследований (укладка 6, ось 10, артефакты 17), у бедра ROI отмечен в 3–4 исследованиях на сторону.
"""
from __future__ import annotations

PERSPECTIVE = {"high": ("высокая", "▲"), "mid": ("средняя", "◆"), "low": ("низкая", "▽"), "none": ("не нужна", "—")}
EDGE_KINDS = {"yes": "да", "no": "нет", "nw": "не сработало", "go": ""}

REGIONS = [
    dict(id="classification", title="classification", ru="классификация", color="#2a78d6", label=(46, 46), lines=["classification"],
         d="M40,150 C30,60 180,20 330,28 C470,36 560,90 548,200 C540,270 520,320 430,334 C300,352 150,330 80,290 C40,260 44,210 40,150 Z"),
    dict(id="regression", title="regression", ru="регрессия", color="#eb6834", label=(1070, 232), lines=["regression"],
         d="M700,300 C720,220 860,190 1010,196 C1160,202 1260,240 1262,320 C1264,420 1220,470 1120,470 C980,470 820,470 740,440 C690,420 684,350 700,300 Z"),
    dict(id="clustering", title="clustering", ru="кластеризация", color="#1baf7a", label=(34, 478), lines=["clustering"],
         d="M20,420 C10,350 90,318 200,318 C330,318 430,370 500,420 C560,470 560,560 520,610 C480,660 380,672 260,670 C120,666 30,620 20,540 Z"),
    dict(id="dimensionality", title="dimensionality reduction", ru="снижение размерности", color="#eda100", label=(1060, 632),
         lines=["dimensionality", "reduction"],
         d="M680,560 C680,490 760,466 880,466 C1010,466 1150,470 1210,520 C1260,560 1262,640 1220,670 C1170,700 1000,700 860,694 C740,690 680,640 680,560 Z"),
]

N = dict  # короткая запись узла

NODES = [
    N(id="start", kind="start", label="START", ru="Старт", x=880, y=120, r=44,
      text="Начало выбора алгоритма.",
      ours="Задача 04: по DICOM определить область, класс качества 0/1 и типы нарушений."),
    N(id="more_data", kind="action", label="get more data", ru="Добыть больше данных", x=618, y=158, r=38,
      text="Меньше 50 примеров — модели учить не на чем.",
      ours="Нужно для бедра: нарушение ROI отмечено в 3–4 исследованиях на сторону, ротация — в 17–19. Запросить разметку у организатора, "
           "аугментации, своя разметка команды.", perspective="high"),
    N(id="d_50", kind="decision", label=">50 samples", ru="Больше 50 примеров?", x=722, y=214, r=38,
      ours="Да: 252 уникальных снимка и 99 исследований позвоночника. Но по классам мало: нарушений 32, по оси 10, по укладке 6."),
    N(id="d_category", kind="decision", label="predicting a category", ru="Предсказываем категорию?", x=628, y=300, r=44,
      ours="Да: класс качества 0/1 и типы нарушений (охват, ось, артефакты, позиционирование и ROI бедра) — мультилейбл."),
    N(id="d_labeled", kind="decision", label="do you have labeled data", ru="Есть размеченные данные?", x=510, y=366, r=46,
      ours="Да: метки экспертов в разметка.xlsx, но на исследование и область, а не на снимок и не контурами."),
    N(id="d_100k_cls", kind="decision", label="<100K samples", ru="Меньше 100 тыс. примеров?", x=478, y=258, r=40,
      ours="Да: сотни снимков — все классические алгоритмы укладываются в секунды."),
    N(id="linear_svc", kind="estimator", region="classification", label="Linear SVC", ru="Линейный SVM", x=368, y=286, w=70, h=48,
      sklearn=["LinearSVC", "LogisticRegression"],
      text="Линейный классификатор: разделяет классы гиперплоскостью в пространстве признаков.",
      used="Нет. Сейчас класс выносят пороги на признаках: угол оси, яркость подвздошных углов, число ярких пикселей.",
      perspective="mid",
      why="Хороший первый шаг на наших признаках снимка вместо ручных порогов: подбирает веса по экспертным меткам. LogisticRegression "
          "из той же ветки сразу даёт вероятность — это ROC-AUC из ТЗ. Нужны class_weight='balanced' (32 нарушения из 99) и разбиение по исследованиям."),
    N(id="d_text", kind="decision", label="Text Data", ru="Это текст?", x=250, y=262, r=40,
      ours="Нет: снимки. Текст пояснений сервис пишет шаблонами."),
    N(id="naive_bayes", kind="estimator", region="classification", label="Naive Bayes", ru="Наивный Байес", x=118, y=232, w=62, h=48,
      sklearn=["GaussianNB", "MultinomialNB"],
      text="Вероятностный классификатор с предположением независимости признаков; классика для текстов.",
      used="Нет.", perspective="low",
      why="Наши признаки сильно связаны (угол, положение оси, яркость краёв), предположение независимости ломается. Годится разве что как контрольный базис."),
    N(id="kneighbors", kind="estimator", region="classification", label="KNeighbors Classifier", ru="k ближайших соседей", x=283, y=152, w=86, h=48,
      sklearn=["KNeighborsClassifier"],
      text="Класс по большинству ближайших по признакам примеров.",
      used="Нет.", perspective="low",
      why="На 99 исследованиях с дисбалансом голосование соседей неустойчиво и чувствительно к масштабу признаков. Плюс — объяснение «похоже на исследования N» для врача, но это можно получить и без классификатора."),
    N(id="svc_ensemble", kind="estimator", region="classification", label="SVC · Ensemble Classifiers", ru="SVM с ядром и ансамбли", x=126, y=130, w=90, h=60,
      sklearn=["SVC(kernel='rbf')", "RandomForestClassifier", "HistGradientBoostingClassifier"],
      text="Нелинейные классификаторы: SVM с ядром и ансамбли деревьев — случайный лес и градиентный бустинг.",
      used="Нет.", perspective="high",
      why="Лучший кандидат для версии с обучением: бустинг и лес работают на сотнях примеров, ловят нелинейность (охват зависит от угла и ширины кадра), "
          "дают вероятности для ROC-AUC и важность признаков для объяснения. Отдельная модель на каждый тип нарушения, class_weight, валидация GroupKFold по исследованиям, бутстреп ДИ."),
    N(id="sgd_cls", kind="estimator", region="classification", label="SGD Classifier", ru="Классификатор на SGD", x=430, y=148, w=64, h=48,
      sklearn=["SGDClassifier"],
      text="Линейные модели, обучаемые стохастическим градиентом, для сотен тысяч примеров и потоков.",
      used="Нет.", perspective="none",
      why="Данных в тысячи раз меньше порога этой ветки; обычные LinearSVC и LogisticRegression решат то же точнее."),
    N(id="kernel_approx_cls", kind="estimator", region="classification", label="kernel approximation", ru="Аппроксимация ядра", x=310, y=82, w=88, h=40,
      sklearn=["Nystroem", "RBFSampler"],
      text="Приближение ядра для нелинейности на больших данных.",
      used="Нет.", perspective="none",
      why="Нужна, когда SVC с ядром не помещается в память; на 252 снимках SVC считается напрямую."),
    N(id="d_quantity", kind="decision", label="predicting a quantity", ru="Предсказываем число?", x=640, y=428, r=44,
      ours="Частично: угол оси и положение Th12 — числа, но их надёжнее считать геометрией, чем учить регрессией без разметки точек."),
    N(id="d_100k_reg", kind="decision", label="<100K samples", ru="Меньше 100 тыс. примеров?", x=752, y=374, r=40,
      ours="Да."),
    N(id="sgd_reg", kind="estimator", region="regression", label="SGD Regressor", ru="Регрессор на SGD", x=820, y=290, w=64, h=48,
      sklearn=["SGDRegressor"], text="Линейная регрессия стохастическим градиентом для больших данных.",
      used="Нет.", perspective="none", why="Не наш масштаб данных."),
    N(id="d_few", kind="decision", label="few features should be important", ru="Важны немногие признаки?", x=922, y=378, r=52,
      ours="Да: из десятков признаков снимка решают единицы — угол, яркость подвздошных углов, яркие пиксели, ширина кадра."),
    N(id="elasticnet", kind="estimator", region="regression", label="ElasticNet · Lasso", ru="ElasticNet и Lasso", x=975, y=274, w=72, h=48,
      sklearn=["Lasso", "ElasticNet"], text="Линейная регрессия с L1-регуляризацией: зануляет лишние признаки.",
      used="Нет.", perspective="low",
      why="Регрессия как таковая нам почти не нужна; L1 полезна для отбора признаков перед классификатором — но то же даёт LogisticRegression(penalty='l1')."),
    N(id="ridge", kind="estimator", region="regression", label="RidgeRegression · SVR(kernel='linear')", ru="Ridge и линейный SVR", x=1085, y=430, w=112, h=60,
      sklearn=["Ridge", "SVR(kernel='linear')"], text="Линейная регрессия с L2-регуляризацией.",
      used="Нет.", perspective="low",
      why="Могла бы предсказывать, например, поправку положения Th12 по профилю яркости, но без разметки точек учить не на чем; геометрия нагляднее."),
    N(id="svr_rbf", kind="estimator", region="regression", label="SVR(kernel='rbf') · EnsembleRegressors", ru="SVR с ядром и ансамбли регрессоров", x=1160, y=320, w=116, h=60,
      sklearn=["SVR(kernel='rbf')", "GradientBoostingRegressor", "RandomForestRegressor"], text="Нелинейная регрессия.",
      used="Нет.", perspective="mid",
      why="Перспективно для координат ориентиров — верх Th12, малый вертел, края ROI бедра — по дескрипторам профилей, если организатор или команда разметят точки хотя бы на сотне снимков. Тогда закроются «охват сверху» и ротация бедра."),
    N(id="d_count_known", kind="decision", label="number of categories known", ru="Число групп известно?", x=405, y=454, r=46,
      ours="Для задачи — да (класс и типы известны); кластеризация у нас вспомогательная: для анализа данных и порогов яркости."),
    N(id="d_10k_clu", kind="decision", label="<10K samples", ru="Меньше 10 тыс. примеров?", x=245, y=490, r=40, ours="Да."),
    N(id="kmeans", kind="estimator", region="clustering", label="KMeans", ru="k-средних", x=234, y=396, w=62, h=40,
      sklearn=["KMeans"], text="Разбивает данные на k групп по близости к центрам.",
      used="Нет. Кость от мягких тканей отделяет порог Отсу по гистограмме.", perspective="mid",
      why="Два применения: KMeans по яркости пикселей как замена порогу Отсу для кости, и группировка снимков по признакам — найти нетипичные кадры, другой аппарат или протокол для отказа «не DXA»."),
    N(id="spectral_gmm", kind="estimator", region="clustering", label="Spectral Clustering · GMM", ru="Спектральная кластеризация и GMM", x=100, y=388, w=86, h=60,
      sklearn=["GaussianMixture", "SpectralClustering"], text="Смесь гауссиан и кластеризация по графу похожести.",
      used="Нет.", perspective="mid",
      why="GaussianMixture на гистограмме яркости даёт мягкий порог кость/фон с вероятностью — устойчивее Отсу на тёмных кадрах и помогает оценке уверенности. Спектральная кластеризация здесь избыточна."),
    N(id="minibatch", kind="estimator", region="clustering", label="MiniBatch KMeans", ru="MiniBatch k-средних", x=212, y=598, w=70, h=48,
      sklearn=["MiniBatchKMeans"], text="KMeans порциями для больших данных.",
      used="Нет.", perspective="none", why="Для пикселей одного снимка и сотен снимков хватает обычного KMeans."),
    N(id="d_10k_clu2", kind="decision", label="<10K samples", ru="Меньше 10 тыс. примеров?", x=470, y=544, r=40, ours="Да."),
    N(id="meanshift", kind="estimator", region="clustering", label="MeanShift · VBGMM", ru="MeanShift и вариационная GMM", x=350, y=622, w=78, h=48,
      sklearn=["MeanShift", "BayesianGaussianMixture"], text="Кластеризация без заданного числа групп.",
      used="Нет.", perspective="low",
      why="Можно сегментировать яркостные области без числа кластеров, но области снимка DXA известны заранее, а MeanShift медленный на пикселях."),
    N(id="tough_luck", kind="action", label="tough luck", ru="Не повезло", x=497, y=660, r=38,
      text="Шпаргалка не знает, что делать.",
      ours="Для снимков выход за пределы scikit-learn — нейросети: см. примечание под схемой."),
    N(id="d_looking", kind="decision", label="just looking", ru="Просто изучаем данные?", x=612, y=540, r=40,
      ours="Да, на этапе анализа: посмотреть структуру набора, дубли и выбросы, разделимость классов."),
    N(id="rpca", kind="estimator", region="dimensionality", label="Randomized PCA", ru="PCA (рандомизированный)", x=765, y=505, w=70, h=48,
      sklearn=["PCA(svd_solver='randomized')"], text="Метод главных компонент: сжимает данные в несколько направлений наибольшей изменчивости.",
      used="Нет.", perspective="mid",
      why="PCA по уменьшенным снимкам 64×64 даёт карту набора и простой детектор аномалий: кадр далеко от облака DXA — кандидат в отказ «не денситометрия». Компоненты можно добавить в признаки классификатора."),
    N(id="d_10k_dim", kind="decision", label="<10K samples", ru="Меньше 10 тыс. примеров?", x=755, y=598, r=40, ours="Да."),
    N(id="isomap", kind="estimator", region="dimensionality", label="Isomap · Spectral Embedding", ru="Isomap и спектральное вложение", x=945, y=538, w=90, h=60,
      sklearn=["Isomap", "SpectralEmbedding"], text="Нелинейное снижение размерности для визуализации многообразий.",
      used="Нет.", perspective="low",
      why="Красивая картинка набора для презентации, но на 252 снимках выигрыша над PCA для решения не даст."),
    N(id="lle", kind="estimator", region="dimensionality", label="LLE", ru="Локально-линейное вложение", x=1085, y=578, w=52, h=40,
      sklearn=["LocallyLinearEmbedding"], text="Нелинейное вложение по локальным окрестностям.",
      used="Нет.", perspective="low", why="То же, что Isomap, и чувствительнее к шуму."),
    N(id="kernel_approx_dim", kind="estimator", region="dimensionality", label="kernel approximation", ru="Аппроксимация ядра", x=940, y=640, w=88, h=40,
      sklearn=["Nystroem", "RBFSampler"], text="Приближённые ядерные признаки для больших данных.",
      used="Нет.", perspective="none", why="Не наш масштаб данных."),
    N(id="d_structure", kind="decision", label="predicting structure", ru="Предсказываем структуру?", x=640, y=660, r=40,
      ours="Нет в терминах scikit-learn; «структура» снимка — контуры позвонков и ROI — это сегментация нейросетью."),
]

EDGES = [
    ("start", "d_50", "go"),
    ("d_50", "more_data", "no"), ("d_50", "d_category", "yes"),
    ("d_category", "d_labeled", "yes"), ("d_category", "d_quantity", "no"),
    ("d_labeled", "d_100k_cls", "yes"), ("d_labeled", "d_count_known", "no"),
    ("d_100k_cls", "linear_svc", "yes"), ("d_100k_cls", "sgd_cls", "no"),
    ("linear_svc", "d_text", "nw"), ("d_text", "naive_bayes", "yes"), ("d_text", "kneighbors", "no"),
    ("kneighbors", "svc_ensemble", "nw"), ("sgd_cls", "kernel_approx_cls", "nw"),
    ("d_quantity", "d_100k_reg", "yes"), ("d_quantity", "d_looking", "no"),
    ("d_100k_reg", "sgd_reg", "no"), ("d_100k_reg", "d_few", "yes"),
    ("d_few", "elasticnet", "yes"), ("d_few", "ridge", "no"), ("ridge", "svr_rbf", "nw"),
    ("d_count_known", "d_10k_clu", "yes"), ("d_count_known", "d_10k_clu2", "no"),
    ("d_10k_clu", "kmeans", "yes"), ("d_10k_clu", "minibatch", "no"), ("kmeans", "spectral_gmm", "nw"),
    ("d_10k_clu2", "meanshift", "yes"), ("d_10k_clu2", "tough_luck", "no"),
    ("d_looking", "rpca", "yes"), ("d_looking", "d_structure", "no"),
    ("rpca", "d_10k_dim", "nw"), ("d_10k_dim", "isomap", "yes"), ("d_10k_dim", "kernel_approx_dim", "no"),
    ("isomap", "lle", "nw"), ("d_structure", "tough_luck", "go"),
]

# путь задачи 04 по схеме: классификация на признаках снимка до SVC и ансамблей
TASK_PATH = ["start", "d_50", "d_category", "d_labeled", "d_100k_cls", "linear_svc", "d_text", "kneighbors", "svc_ensemble"]

BEYOND = [
    dict(title="Нейросети для снимков (не scikit-learn)", perspective="high",
         text="U-Net или лёгкая CNN на PyTorch для сегментации позвонков, подвздошных костей, вертелов и ROI — закрывают Th12, ротацию и поля ROI. "
              "Нужна разметка контуров или точек хотя бы на сотне снимков; инференс локально в контейнере укладывается в требования ТЗ."),
    dict(title="Что работает сейчас", perspective=None,
         text="Правила на numpy: профиль яркости вдоль оси, порог Отсу, скользящая медиана, центры позвонков и угол оси, яркость в углах кадра, "
              "поиск очень ярких объектов. Итог по позвоночнику F1 0,45 на обучающем наборе."),
    dict(title="Рекомендуемый следующий шаг", perspective="high",
         text="Признаки, которые уже считает анализ, плюс HistGradientBoostingClassifier и LogisticRegression по типам нарушений с GroupKFold по исследованиям, "
              "class_weight и калибровкой вероятностей: даст ROC-AUC и честные ДИ; порог по F1 подбирать на валидации, а не на всех данных."),
]


def node_map() -> dict:
    return {n["id"]: n for n in NODES}


def estimators() -> list[dict]:
    order = {"high": 0, "mid": 1, "low": 2, "none": 3}
    return sorted((n for n in NODES if n["kind"] == "estimator"), key=lambda n: (order[n["perspective"]], n["label"]))


def payload() -> dict:
    return dict(nodes=NODES, edges=[dict(src=a, dst=b, kind=k) for a, b, k in EDGES], regions=REGIONS, path=TASK_PATH,
                perspective={k: dict(label=v[0], icon=v[1]) for k, v in PERSPECTIVE.items()}, edge_kinds=EDGE_KINDS)
