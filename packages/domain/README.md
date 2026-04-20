# packages/domain

Каталог для shared domain vocabulary/value objects/portable rules, которые могут понадобиться вне Python runtime.

Примерно сюда могут быть вынесены:

- коды статусов и reason codes;
- словари доменных сущностей;
- portable validation enums;
- contract-friendly domain constants.

Доменные вычисления и бизнес-логика по-прежнему остаются в `src/core/`, пока нет осознанной причины выносить что-либо в cross-platform package.
